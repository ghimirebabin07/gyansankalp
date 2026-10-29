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
from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.storage import Storage, get_storage
from app.db.session import SessionLocal
from app.models.material import Material, MaterialStatus

log = logging.getLogger("worker")

MAX_ATTEMPTS = 3
STALE_AFTER = timedelta(minutes=10)  # a job "processing" longer than this is treated as crashed
POLL_SECONDS = 3
TARGET_LONG_SIDE = 1700              # pixels on the longest side of a page image
MAX_ZOOM = 3.0                       # stops tiny pages from being blown up


class PermanentError(Exception):
    """The PDF itself is bad. Retrying will not help."""


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
        .values(status=MaterialStatus.failed, error="Conversion kept failing or the worker crashed")
    )

    stmt = (
        select(Material)
        .where(
            Material.attempts < MAX_ATTEMPTS,
            or_(
                Material.status == MaterialStatus.pending,
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
    db.commit()


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
            material = db.get(Material, material_id)
            if material:
                material.error = str(exc)[:500]
                give_up = permanent or material.attempts >= MAX_ATTEMPTS
                material.status = MaterialStatus.failed if give_up else MaterialStatus.pending
                db.commit()
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    storage = get_storage()
    stop = False

    def _stop(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    log.info("worker started")
    while not stop:
        try:
            worked = run_once(storage)
        except Exception:
            log.exception("worker loop error")
            worked = False
        if not worked:
            time.sleep(POLL_SECONDS)
    log.info("worker stopped")


if __name__ == "__main__":
    main()
