"""Background worker: turns uploaded PDFs into page images.

Run it as its own process (never inside the web app):

    python -m app.worker
"""
import io
import logging
import signal
import tempfile
import time
from datetime import datetime, timedelta, timezone

import pymupdf
from PIL import Image
from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.observability import configure_logging
from app.core.storage import Storage, get_storage
from app.db.session import SessionLocal
from app.models.access_log import AccessLog
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.models.material import Material, MaterialStatus
from app.models.refresh_token import RefreshToken

log = logging.getLogger("worker")

MAX_ATTEMPTS = 3
STALE_AFTER = timedelta(minutes=10)  # a job "processing" longer than this is treated as crashed
POLL_SECONDS = 3
BACKOFF_BASE = timedelta(seconds=30)  # retries wait 30s, then 60s, then 120s
MAINTENANCE_EVERY = timedelta(minutes=15)
TARGET_LONG_SIDE = 1700              # pixels on the longest side of a page image
MAX_ZOOM = 3.0                       # stops tiny pages from being blown up


class PermanentError(Exception):
    """The PDF itself is bad. Retrying will not help."""


def backoff_for(attempts: int) -> timedelta:
    return BACKOFF_BASE * (2 ** max(0, attempts - 1))


def claim_next(db: Session) -> int | None:
    """Atomically take one job. SKIP LOCKED lets several workers run safely."""
    now = datetime.now(timezone.utc)
    stale = now - STALE_AFTER

    # Idempotent cleanup: give up on jobs that crashed too many times.
    db.execute(
        update(Material)
        .where(
            Material.status == MaterialStatus.processing,
            Material.attempts >= MAX_ATTEMPTS,
            Material.processing_started_at < stale,
        )
        .values(
            status=MaterialStatus.failed,
            error="Conversion kept failing or the worker crashed",
            next_attempt_at=None,
        )
    )

    stmt = (
        select(Material)
        .where(
            Material.attempts < MAX_ATTEMPTS,
            or_(
                and_(
                    Material.status == MaterialStatus.pending,
                    or_(
                        Material.next_attempt_at.is_(None),
                        Material.next_attempt_at <= now,
                    ),
                ),
                and_(
                    Material.status == MaterialStatus.processing,
                    Material.processing_started_at < stale,
                ),
            ),
        )
        .order_by(Material.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    material = db.scalar(stmt)
    if material is None:
        db.commit()
        return None

    material.status = MaterialStatus.processing
    material.attempts += 1
    material.processing_started_at = now
    material.next_attempt_at = None
    material_id = material.id
    db.commit()
    return material_id


def convert(db: Session, material_id: int, storage: Storage) -> None:
    material = db.get(Material, material_id)
    with tempfile.TemporaryDirectory() as tmp:
        path = f"{tmp}/in.pdf"
        storage.download_to_path(material.original_key, path)

        try:
            doc = pymupdf.open(path)
        except Exception as exc:
            raise PermanentError("Cannot read this PDF (corrupt or not a PDF)") from exc

        with doc:
            if doc.needs_pass:
                raise PermanentError("PDF is password protected")
            count = doc.page_count
            if count == 0:
                raise PermanentError("PDF has no pages")
            if count > settings.max_pdf_pages:
                raise PermanentError(f"PDF has {count} pages, the limit is {settings.max_pdf_pages}")

            for i in range(count):
                page = doc.load_page(i)
                longest = max(page.rect.width, page.rect.height) or 1
                zoom = min(MAX_ZOOM, TARGET_LONG_SIDE / longest)  # caps huge pages too
                pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                buf = io.BytesIO()
                img.save(buf, "JPEG", quality=85, optimize=True)
                # Fixed keys: running the same job twice just overwrites the same files.
                storage.put_bytes(f"pages/{material_id}/{i + 1}.jpg", buf.getvalue(), "image/jpeg")

    material.page_count = count
    material.status = MaterialStatus.ready
    material.error = None
    material.next_attempt_at = None
    db.commit()


def mark_failed(db: Session, material_id: int, message: str, *, permanent: bool) -> bool:
    """Record the error and decide whether the job waits or is done failing."""
    material = db.get(Material, material_id)
    if material is None:
        return False
    material.error = message[:500]
    give_up = permanent or material.attempts >= MAX_ATTEMPTS
    if give_up:
        material.status = MaterialStatus.failed
        material.next_attempt_at = None
    else:
        material.status = MaterialStatus.pending
        material.next_attempt_at = datetime.now(timezone.utc) + backoff_for(material.attempts)
    db.commit()
    return give_up


def run_once(storage: Storage) -> bool:
    """Process at most one job. Returns True if a job was taken."""
    with SessionLocal() as db:
        material_id = claim_next(db)
    if material_id is None:
        return False

    with SessionLocal() as db:
        try:
            convert(db, material_id, storage)
            log.info("material %s is ready", material_id)
        except Exception as exc:
            db.rollback()
            permanent = isinstance(exc, PermanentError)
            if not permanent:
                log.exception("material %s failed", material_id)
            gave_up = mark_failed(db, material_id, str(exc), permanent=permanent)
            if gave_up:
                log.warning("material %s marked failed after %s attempt(s)", material_id, MAX_ATTEMPTS)
    return True


def run_maintenance() -> None:
    """Trim tables that otherwise grow forever. Each statement uses an existing index."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        lapsed = db.execute(
            update(Enrollment)
            .where(
                Enrollment.status == EnrollmentStatus.active,
                Enrollment.expires_at.is_not(None),
                Enrollment.expires_at <= now,
            )
            .values(status=EnrollmentStatus.expired)
        ).rowcount

        # Dead tokens lose their value at expiry, so the purge only needs to look
        # at expires_at. A revoked one lingers harmlessly until then.
        tokens = db.execute(
            delete(RefreshToken).where(
                RefreshToken.expires_at < now - timedelta(days=settings.refresh_token_purge_days)
            )
        ).rowcount

        logs = db.execute(
            delete(AccessLog).where(
                AccessLog.created_at < now - timedelta(days=settings.access_log_days)
            )
        ).rowcount
        db.commit()

    if lapsed or tokens or logs:
        log.info(
            "maintenance: %s enrollment(s) expired, %s token(s) purged, %s access log(s) pruned",
            lapsed, tokens, logs,
        )


def main() -> None:
    configure_logging()
    storage = get_storage()
    stop = False

    def _stop(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    log.info("worker started")
    next_maintenance = datetime.now(timezone.utc)
    while not stop:
        try:
            worked = run_once(storage)
        except Exception:
            log.exception("worker loop error")
            worked = False

        if datetime.now(timezone.utc) >= next_maintenance:
            next_maintenance = datetime.now(timezone.utc) + MAINTENANCE_EVERY
            try:
                run_maintenance()
            except Exception:
                log.exception("maintenance failed")

        if not worked:
            time.sleep(POLL_SECONDS)
    log.info("worker stopped")


if __name__ == "__main__":
    main()
