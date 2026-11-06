"""Worker fault tolerance: retries wait, crashed jobs are reclaimed, tables get pruned.

These tests delete rows, so they only run against a throwaway database.
"""
import io
import tempfile
from datetime import datetime, timedelta, timezone

import pymupdf
import pytest
from PIL import Image
from sqlalchemy import delete, select, text, update

from app import worker
from app.core.config import settings
from app.db.session import SessionLocal, engine
from app.models.access_log import AccessLog
from app.models.course import Course, Topic
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.models.material import Material, MaterialStatus
from app.models.refresh_token import RefreshToken
from app.models.user import User

TABLES = ("access_logs", "materials", "refresh_tokens", "enrollments", "users", "topics", "courses")


def now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture(scope="module")
def db():
    name = (engine.url.database or "").lower()
    if settings.app_env == "production" or not ("test" in name or name.endswith("_ci")):
        pytest.skip(f"{name!r} is not a throwaway database and these tests delete rows")
    session = SessionLocal()
    try:
        for table in TABLES:
            session.execute(text(f"DELETE FROM {table}"))
        session.commit()
        course = Course(title="Worker", slug="worker-course", exam_level="kharidar", is_published=True)
        other = Course(title="Worker Two", slug="worker-course-2", exam_level="nasu", is_published=True)
        user = User(full_name="Worker Student", email="worker-test@example.com",
                    phone="9800000001", password_hash="x", role="student")
        session.add_all([course, other, user])
        session.commit()
        topic = Topic(course_id=course.id, title="Chapter 1", position=1)
        session.add(topic)
        session.commit()
        session.course_id = course.id
        session.other_course_id = other.id
        session.topic_id = topic.id
        session.user_id = user.id
        yield session
    finally:
        for table in TABLES:
            session.execute(text(f"DELETE FROM {table}"))
        session.commit()
        session.close()


@pytest.fixture(autouse=True)
def clean_materials(db):
    db.execute(update(Material).values(status=MaterialStatus.ready, attempts=0,
                                       next_attempt_at=None, processing_started_at=None))
    db.execute(delete(Material))
    db.commit()
    return db


def add_material(db, **values) -> int:
    row = Material(topic_id=db.topic_id, title="chapter.pdf",
                   original_key=f"orig/{values.get('title', 'x')}-{now():%H%M%S%f}",
                   size_bytes=1000, **values)
    db.add(row)
    db.commit()
    return row.id


def reload_material(db, material_id: int) -> Material:
    db.expire_all()
    return db.get(Material, material_id)


class AlwaysFails:
    """Stand-in for a conversion that dies the same way twice."""

    def __init__(self, error: Exception):
        self.error = error

    def __call__(self, db, material_id, storage):
        raise self.error


def test_backoff_grows_exponentially():
    assert worker.backoff_for(1) == timedelta(seconds=30)
    assert worker.backoff_for(2) == timedelta(seconds=60)
    assert worker.backoff_for(3) == timedelta(seconds=120)


def test_a_job_still_in_backoff_is_left_alone(clean_materials):
    db = clean_materials
    add_material(db, status=MaterialStatus.pending, next_attempt_at=now() + timedelta(hours=1))
    assert worker.claim_next(db) is None


def test_a_job_whose_wait_is_over_is_claimed(clean_materials):
    db = clean_materials
    material_id = add_material(db, status=MaterialStatus.pending,
                               next_attempt_at=now() - timedelta(seconds=1))
    assert worker.claim_next(db) == material_id


def test_a_retryable_failure_waits_before_the_next_attempt(clean_materials, monkeypatch):
    db = clean_materials
    material_id = add_material(db, status=MaterialStatus.pending)
    monkeypatch.setattr(worker, "convert", AlwaysFails(RuntimeError("temp file vanished")))
    assert worker.run_once(storage=None) is True

    row = reload_material(db, material_id)
    assert row.status == MaterialStatus.pending
    assert row.attempts == 1
    assert row.next_attempt_at > now() + timedelta(seconds=20)
    assert "temp file vanished" in row.error


def test_a_corrupt_pdf_fails_at_once_without_retrying(clean_materials, monkeypatch):
    db = clean_materials
    material_id = add_material(db, status=MaterialStatus.pending)
    monkeypatch.setattr(worker, "convert",
                        AlwaysFails(worker.PermanentError("PDF is password protected")))
    worker.run_once(storage=None)

    row = reload_material(db, material_id)
    assert row.status == MaterialStatus.failed
    assert row.next_attempt_at is None


def test_the_last_attempt_gives_up_instead_of_retrying(clean_materials, monkeypatch):
    db = clean_materials
    material_id = add_material(db, status=MaterialStatus.pending, attempts=worker.MAX_ATTEMPTS - 1)
    monkeypatch.setattr(worker, "convert", AlwaysFails(RuntimeError("still broken")))
    worker.run_once(storage=None)

    row = reload_material(db, material_id)
    assert row.status == MaterialStatus.failed
    assert row.attempts == worker.MAX_ATTEMPTS


def test_a_job_left_by_a_crashed_worker_is_reclaimed(clean_materials):
    db = clean_materials
    material_id = add_material(db, status=MaterialStatus.processing, attempts=1,
                               processing_started_at=now() - timedelta(hours=2))
    assert worker.claim_next(db) == material_id
    row = reload_material(db, material_id)
    assert row.attempts == 2
    assert row.status == MaterialStatus.processing


def test_a_job_that_already_used_its_attempts_is_given_up_on(clean_materials):
    db = clean_materials
    material_id = add_material(db, status=MaterialStatus.processing, attempts=worker.MAX_ATTEMPTS,
                               processing_started_at=now() - timedelta(hours=2))
    assert worker.claim_next(db) is None
    assert reload_material(db, material_id).status == MaterialStatus.failed


def test_a_fresh_conversion_is_not_stolen_from_the_worker_holding_it(clean_materials):
    db = clean_materials
    material_id = add_material(db, status=MaterialStatus.processing, attempts=1,
                               processing_started_at=now() - timedelta(minutes=1))
    assert worker.claim_next(db) is None
    assert reload_material(db, material_id).attempts == 1


def test_maintenance_stops_lapsed_access_and_keeps_live_access(clean_materials):
    db = clean_materials
    lapsed = Enrollment(user_id=db.user_id, course_id=db.course_id, status=EnrollmentStatus.active,
                        expires_at=now() - timedelta(days=1))
    live = Enrollment(user_id=db.user_id, course_id=db.other_course_id,
                      status=EnrollmentStatus.active, expires_at=now() + timedelta(days=30))
    db.add_all([lapsed, live])
    db.commit()

    worker.run_maintenance()
    db.expire_all()
    assert db.get(Enrollment, lapsed.id).status == EnrollmentStatus.expired
    assert db.get(Enrollment, live.id).status == EnrollmentStatus.active

    db.delete(lapsed)
    db.delete(live)
    db.commit()


def test_maintenance_prunes_dead_tokens_and_old_page_views(clean_materials):
    db = clean_materials
    dead_token = RefreshToken(user_id=db.user_id, token_hash="a" * 64,
                              expires_at=now() - timedelta(days=40))
    live_token = RefreshToken(user_id=db.user_id, token_hash="b" * 64,
                              expires_at=now() + timedelta(days=1))
    old_view = AccessLog(user_id=db.user_id, page_no=1,
                         created_at=now() - timedelta(days=settings.access_log_days + 10))
    recent_view = AccessLog(user_id=db.user_id, page_no=2, created_at=now())
    db.add_all([dead_token, live_token, old_view, recent_view])
    db.commit()

    worker.run_maintenance()
    db.expire_all()
    assert db.scalar(select(RefreshToken).where(RefreshToken.token_hash == "a" * 64)) is None
    assert db.scalar(select(RefreshToken).where(RefreshToken.token_hash == "b" * 64)) is not None
    remaining = db.scalars(select(AccessLog)).all()
    assert [v.page_no for v in remaining] == [2]


# ---- what the converter refuses to spend its time on ----

def a_pdf(pages: int = 1, *, side: int = 200, encrypted: bool = False) -> bytes:
    doc = pymupdf.open()
    for _ in range(pages):
        doc.new_page(width=side, height=side)
    if not encrypted:
        return doc.tobytes()
    path = f"{tempfile.mkdtemp()}/locked.pdf"
    doc.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    doc.close()
    with open(path, "rb") as handle:
        return handle.read()


class LocalStorage:
    """The bytes a conversion would read from the bucket, and the keys it writes."""

    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.pages: dict[str, bytes] = {}

    def download_to_path(self, key: str, path: str) -> None:
        with open(path, "wb") as handle:
            handle.write(self.payload)

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        self.pages[key] = data


def test_a_pdf_over_the_page_ceiling_is_refused_before_rendering(clean_materials, monkeypatch):
    """A 20 000-page PDF is a free denial of service if the limit is checked late.

    Rendered pages are the expensive part: the count is read first so the job
    fails without drawing a single one.
    """
    db = clean_materials
    monkeypatch.setattr(settings, "max_pdf_pages", 3)
    material_id = add_material(db, status=MaterialStatus.processing)
    storage = LocalStorage(a_pdf(pages=4))

    with pytest.raises(worker.PermanentError, match="the limit is 3"):
        worker.convert(db, material_id, storage)
    assert storage.pages == {}


def test_a_locked_or_forged_pdf_fails_without_retries(clean_materials):
    db = clean_materials
    for payload, message in ((a_pdf(encrypted=True), "password protected"),
                             (b"%PDF-1.7\nthis is not a document\n", "Cannot read")):
        material_id = add_material(db, status=MaterialStatus.processing)
        with pytest.raises(worker.PermanentError, match=message):
            worker.convert(db, material_id, LocalStorage(payload))


def test_an_enormous_page_is_drawn_down_to_the_size_cap(clean_materials):
    """A page can be declared 20 000 points wide; the image cannot be that big."""
    db = clean_materials
    material_id = add_material(db, status=MaterialStatus.processing)
    storage = LocalStorage(a_pdf(pages=1, side=20000))

    worker.convert(db, material_id, storage)

    image = Image.open(io.BytesIO(storage.pages[f"pages/{material_id}/1.jpg"]))
    assert max(image.size) <= worker.TARGET_LONG_SIDE
    row = reload_material(db, material_id)
    assert row.status == MaterialStatus.ready
    assert row.page_count == 1
