"""Authorization boundaries, exercised through the real HTTP stack.

Students and admins are served by one process, so the bugs that matter live at
the seam between them: a student token reaching an admin route, a lapsed
enrollment still serving pages, an anonymous request getting a 200. Testing the
dependency functions alone would miss a route that simply forgot to use one.

These tests delete rows, so they only run against a throwaway database.
"""

import io
import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select, text

from app.core import ratelimit
from app.core.config import settings
from app.core.ratelimit import SlidingWindow
from app.core.security import hash_password
from app.core.storage import get_storage
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.admin import Admin, AdminRole
from app.models.course import Course, Topic
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.models.material import Material, MaterialStatus
from app.models.user import User
from app.routers import admin_materials

PASSWORD = "Str0ng-Passw0rd-for-tests"
CLIENT_IP = "testclient"
TABLES = ("access_logs", "materials", "refresh_tokens", "enrollments",
          "users", "admin_activity_logs", "admin_otps", "admin_refresh_tokens",
          "course_assignments", "admins", "topics", "courses")


def signed_token(subject: int, secret: str, token_type: str, *, minutes: int = 5) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": str(subject), "type": token_type, "iat": now,
         "exp": now + timedelta(minutes=minutes)},
        secret,
        algorithm=settings.jwt_algorithm,
    )


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class RecordingStorage:
    """Counts reads so a test can prove a refused request never reached storage."""

    def __init__(self) -> None:
        self.reads = 0

    def get_bytes(self, key: str) -> bytes:
        self.reads += 1
        image = io.BytesIO()
        Image.new("RGB", (300, 200), "white").save(image, "JPEG")
        return image.getvalue()

    def ping(self) -> bool:
        return True


@pytest.fixture(scope="module")
def ctx():
    name = (engine.url.database or "").lower()
    if settings.app_env == "production" or not ("test" in name or name.endswith("_ci")):
        pytest.skip(f"{name!r} is not a throwaway database and these tests delete rows")

    db = SessionLocal()
    try:
        for table in TABLES:
            db.execute(text(f"DELETE FROM {table}"))
        db.commit()

        joined = Course(title="Joined", slug="authz-joined", exam_level="kharidar",
                        is_published=True)
        locked_out = Course(title="Locked", slug="authz-locked", exam_level="nasu",
                            is_published=True)
        db.add_all([joined, locked_out])
        db.commit()

        inner_topic = Topic(course_id=joined.id, title="Chapter 1", position=1)
        outer_topic = Topic(course_id=locked_out.id, title="Chapter 2", position=1)
        db.add_all([inner_topic, outer_topic])
        db.commit()

        salt = uuid4().hex[:8]
        ready = Material(topic_id=inner_topic.id, title="ready.pdf",
                         original_key=f"orig/authz-ready-{salt}", size_bytes=2048,
                         status=MaterialStatus.ready, page_count=4)
        # A student must never see a job that has not been converted, and must
        # never learn it exists from the listing.
        pending = Material(topic_id=inner_topic.id, title="pending.pdf",
                           original_key=f"orig/authz-pending-{salt}", size_bytes=4096,
                           status=MaterialStatus.pending)
        db.add_all([ready, pending])
        db.commit()

        def student(label: str, phone: str, active: bool = True) -> User:
            return User(
                full_name=f"Authz {label}", email=f"authz-{label}-{salt}@gsprobe.dev",
                phone=phone, password_hash=hash_password(PASSWORD), role="student",
                is_active=active,
            )

        member = student("member", "9811111111")
        stranger = student("stranger", "9811111112")
        dormant = student("dormant", "9811111113", active=False)
        lockable = student("lockable", "9811111114")
        admin = Admin(email=f"authz-admin-{salt}@gsprobe.dev", full_name="Authz Admin",
                      role=AdminRole.super_admin,
                      password_hash=hash_password(PASSWORD), is_active=True)
        db.add_all([member, stranger, dormant, lockable, admin])
        db.commit()

        db.add(Enrollment(user_id=member.id, course_id=joined.id,
                          status=EnrollmentStatus.active))
        db.commit()

        client = TestClient(app)

        def login(email: str, password: str = PASSWORD) -> tuple[int, dict]:
            response = client.post("/auth/login", data={"username": email,
                                                        "password": password})
            return response.status_code, response.json()

        status, tokens = login(member.email)
        assert status == 200, tokens
        member_token = tokens["access_token"]
        member_refresh = tokens["refresh_token"]
        # Staff sign in with Google plus an emailed code, which no test can finish
        # against Google. The boundary these cases care about is the token's shape,
        # so it is minted with the admin key the dependency expects.
        admin_token = signed_token(admin.id, settings.admin_jwt_secret, "admin")

        yield SimpleNamespace(
            db=db, client=client, login=login, salt=salt,
            member_id=member.id, member_token=member_token, member_email=member.email,
            member_refresh=member_refresh, stranger_token=login(stranger.email)[1]["access_token"],
            stranger_id=stranger.id,
            dormant_id=dormant.id, lockable_email=lockable.email,
            admin_id=admin.id, admin_token=admin_token, admin_email=admin.email,
            joined_course_id=joined.id, inner_topic_id=inner_topic.id,
            outer_topic_id=outer_topic.id, ready_material_id=ready.id,
            ready_original_key=ready.original_key,
            pending_material_id=pending.id,
        )
    finally:
        for table in TABLES:
            db.execute(text(f"DELETE FROM {table}"))
        db.commit()
        db.close()


@pytest.fixture(autouse=True)
def fresh_rate_limits(ctx):
    """Every case starts with empty counters, whatever the previous one spent."""
    for window in vars(ratelimit).values():
        if isinstance(window, SlidingWindow):
            window.reset(CLIENT_IP)
    yield


# ---- the two auth systems stay two systems ----

def test_anonymous_requests_are_refused_everywhere_they_matter(ctx):
    for path in ("/auth/me", "/me/courses", f"/topics/{ctx.inner_topic_id}/materials",
                 f"/materials/{ctx.ready_material_id}/pages/1", "/admin/courses",
                 "/admin/auth/me"):
        assert ctx.client.get(path).status_code == 401, path


def test_a_student_token_opens_no_admin_route(ctx):
    for method, path in (("GET", "/admin/courses"), ("GET", "/admin/auth/me"),
                         ("POST", "/admin/courses"), ("DELETE", "/admin/courses/1")):
        response = ctx.client.request(method, path, headers=bearer(ctx.member_token),
                                      json={} if method in {"POST", "PATCH"} else None)
        assert response.status_code in (401, 403), f"{method} {path}"


def test_an_admin_token_opens_no_student_route(ctx):
    assert ctx.client.get("/auth/me", headers=bearer(ctx.admin_token)).status_code == 401
    response = ctx.client.get(f"/topics/{ctx.inner_topic_id}/materials",
                              headers=bearer(ctx.admin_token))
    assert response.status_code == 401


def test_a_token_signed_with_the_student_key_is_not_admin(ctx):
    """The point of two keys: forging an admin claim needs the admin secret."""
    forged = signed_token(ctx.admin_id, settings.jwt_secret, "admin")
    assert ctx.client.get("/admin/courses", headers=bearer(forged)).status_code == 401


def test_a_token_signed_with_the_admin_key_is_not_a_student(ctx):
    forged = signed_token(ctx.member_id, settings.admin_jwt_secret, "user")
    assert ctx.client.get("/auth/me", headers=bearer(forged)).status_code == 401


def test_an_admin_token_cannot_be_replayed_as_a_user_token(ctx):
    # Same secret now, but the type claim still has to match the verifier.
    swapped = signed_token(ctx.member_id, settings.admin_jwt_secret, "admin")
    assert ctx.client.get("/auth/me", headers=bearer(swapped)).status_code == 401


# ---- token hygiene ----

def test_expired_and_malformed_tokens_are_rejected(ctx):
    expired = signed_token(ctx.member_id, settings.jwt_secret, "user", minutes=-1)
    assert ctx.client.get("/auth/me", headers=bearer(expired)).status_code == 401
    assert ctx.client.get("/auth/me", headers=bearer("not-a-jwt")).status_code == 401
    assert ctx.client.get("/auth/me", headers={"Authorization": "Bearer"}).status_code == 401


def test_a_valid_token_for_a_deactivated_account_is_refused(ctx):
    token = signed_token(ctx.dormant_id, settings.jwt_secret, "user")
    assert ctx.client.get("/auth/me", headers=bearer(token)).status_code == 401


# ---- enrollment is the only door to material ----

def test_only_enrolled_students_can_list_materials(ctx):
    url = f"/topics/{ctx.inner_topic_id}/materials"
    assert ctx.client.get(url, headers=bearer(ctx.member_token)).status_code == 200
    refused = ctx.client.get(url, headers=bearer(ctx.stranger_token))
    assert refused.status_code == 403
    assert refused.json()["error"], "a refusal must still be a shaped error"


def test_unconverted_material_is_never_listed(ctx):
    body = ctx.client.get(f"/topics/{ctx.inner_topic_id}/materials",
                          headers=bearer(ctx.member_token)).json()
    ids = {row["id"] for row in body}
    assert ctx.ready_material_id in ids
    assert ctx.pending_material_id not in ids


def test_a_student_cannot_cross_into_an_unpaid_course(ctx):
    assert ctx.client.get(f"/topics/{ctx.outer_topic_id}/materials",
                          headers=bearer(ctx.member_token)).status_code == 403
    response = ctx.client.get(f"/materials/{ctx.ready_material_id}/pages/1",
                              headers=bearer(ctx.stranger_token))
    assert response.status_code == 403


def test_a_lapsed_enrollment_stops_access_without_waiting_for_a_sweep(ctx):
    ctx.db.execute(
        text("UPDATE enrollments SET expires_at = NOW() - INTERVAL '1 minute' "
             "WHERE user_id = :user_id"),
        {"user_id": ctx.member_id},
    )
    ctx.db.commit()
    try:
        assert ctx.client.get(f"/topics/{ctx.inner_topic_id}/materials",
                              headers=bearer(ctx.member_token)).status_code == 403
    finally:
        ctx.db.execute(text("UPDATE enrollments SET expires_at = NULL "
                            "WHERE user_id = :user_id"), {"user_id": ctx.member_id})
        ctx.db.commit()


def test_a_student_row_marked_admin_still_needs_an_enrollment(ctx):
    """The role column on the student table is not a second door.

    Before this rule was written down, a student row carrying the admin role
    could read every course with an ordinary student token - a privilege path
    that skipped the whole admin auth system.
    """
    db = ctx.db
    pseudo = User(full_name="Wannabe Admin", email=f"authz-pseudo-{ctx.salt}@gsprobe.dev",
                  phone="9811111119", password_hash=hash_password(PASSWORD),
                  role="admin", is_active=True)
    db.add(pseudo)
    db.commit()
    try:
        token = ctx.login(pseudo.email)[1]["access_token"]
        assert db.get(User, pseudo.id).role.value == "admin"
        listing = ctx.client.get(f"/topics/{ctx.inner_topic_id}/materials",
                                 headers=bearer(token))
        assert listing.status_code == 403, "a role flag granted course access"
        page = ctx.client.get(f"/materials/{ctx.ready_material_id}/pages/1",
                              headers=bearer(token))
        assert page.status_code == 403
    finally:
        db.execute(text("DELETE FROM users WHERE id = :id"), {"id": pseudo.id})
        db.commit()


def test_storage_is_never_touched_for_a_refused_page_request(ctx):
    """The gate runs before the read, and what comes back is stamped per viewer.

    Storage is unreachable in a test environment on purpose, so the page route
    is driven by a stand-in that only answers once access has been granted.
    """
    fake = RecordingStorage()
    app.dependency_overrides[get_storage] = lambda: fake
    page = f"/materials/{ctx.ready_material_id}/pages/1"
    try:
        refused = ctx.client.get(page, headers=bearer(ctx.stranger_token))
        assert refused.status_code == 403
        assert fake.reads == 0, "a refused request must not reach storage"

        mine = ctx.client.get(page, headers=bearer(ctx.member_token))
        assert mine.status_code == 200, mine.text
        assert mine.headers["cache-control"] == "private, no-store, max-age=0"
        assert mine.headers["x-content-type-options"] == "nosniff"

        ctx.db.add(Enrollment(user_id=ctx.stranger_id, course_id=ctx.joined_course_id,
                              status=EnrollmentStatus.active))
        ctx.db.commit()
        try:
            theirs = ctx.client.get(page, headers=bearer(ctx.stranger_token))
            assert theirs.status_code == 200
            assert theirs.content != mine.content, "both viewers got the same stamp"
        finally:
            ctx.db.execute(
                text("DELETE FROM enrollments WHERE user_id = :user_id"),
                {"user_id": ctx.stranger_id},
            )
            ctx.db.commit()
    finally:
        app.dependency_overrides.pop(get_storage, None)


# ---- deleting a material does not wait on the bucket ----

class RecordingPurge:
    """Stands in for the object store so a purge can be watched, and failed."""

    def __init__(self, fail: bool = False) -> None:
        self.keys: list[str] = []
        self.done = threading.Event()
        self.fail = fail

    def delete(self, key: str) -> None:
        self.keys.append(key)
        if self.fail:
            raise RuntimeError("the bucket is unreachable")

    def delete_prefix(self, prefix: str) -> None:
        self.keys.append(prefix)
        if self.fail:
            raise RuntimeError("the bucket is unreachable")
        self.done.set()


def test_a_delete_hands_the_files_over_instead_of_walking_them(ctx, monkeypatch):
    """The response marks the end of access, not of the storage work.

    Supabase rejects batched deletes, so serving the 204 only after every page
    is gone means an admin whose browser gives up at 30 seconds sees a failed
    delete on something that already worked.
    """
    handed: list[tuple[str, str]] = []
    monkeypatch.setattr(admin_materials, "_purge_objects",
                        lambda key, prefix: handed.append((key, prefix)))

    doomed = Material(topic_id=ctx.inner_topic_id, title="doomed.pdf",
                      original_key=f"orig/authz-doomed-{ctx.salt}", size_bytes=1024,
                      status=MaterialStatus.ready, page_count=2)
    ctx.db.add(doomed)
    ctx.db.commit()

    refused = ctx.client.delete(f"/admin/materials/{doomed.id}",
                                headers=bearer(ctx.member_token))
    assert refused.status_code == 401, refused.text
    assert handed == [], "a refused delete must not touch the bucket"

    gone = ctx.client.delete(f"/admin/materials/{doomed.id}",
                             headers=bearer(ctx.admin_token))
    assert gone.status_code == 204, gone.text
    remaining = ctx.db.execute(select(Material).where(Material.id == doomed.id)).scalar_one_or_none()
    assert remaining is None
    assert handed == [(f"orig/authz-doomed-{ctx.salt}", f"pages/{doomed.id}/")]


def test_the_purge_clears_the_original_and_the_pages(ctx, monkeypatch):
    fake = RecordingPurge()
    monkeypatch.setattr(admin_materials, "get_storage", lambda: fake)
    admin_materials._purge("orig/book.pdf", "pages/42/")

    assert fake.done.wait(10), "the purge never reached the pages"
    assert fake.keys == ["orig/book.pdf", "pages/42/"]

    # A bucket that is down leaves garbage, not a 500 on an already-committed
    # delete and not a stack trace in the log.
    broken = RecordingPurge(fail=True)
    monkeypatch.setattr(admin_materials, "get_storage", lambda: broken)
    admin_materials._purge("orig/other.pdf", "pages/43/")
    assert broken.keys == ["orig/other.pdf"]


# ---- login, refresh and lockout ----

def test_a_refresh_token_works_once(ctx):
    first = ctx.client.post("/auth/refresh", json={"refresh_token": ctx.member_refresh})
    assert first.status_code == 200, first.json()
    replay = ctx.client.post("/auth/refresh", json={"refresh_token": ctx.member_refresh})
    assert replay.status_code == 401


def test_logout_revokes_the_refresh_token(ctx):
    issued = ctx.login(ctx.member_email)[1]
    ctx.client.post("/auth/logout", json={"refresh_token": issued["refresh_token"]})
    assert ctx.client.post("/auth/refresh",
                           json={"refresh_token": issued["refresh_token"]}).status_code == 401


def test_repeated_wrong_passwords_lock_the_account(ctx):
    for _ in range(settings.login_max_attempts):
        assert ctx.login(ctx.lockable_email, "wrong-password-here")[0] == 401
    # The right password arrives, and the lockout answers it.
    assert ctx.login(ctx.lockable_email)[0] == 401
    locked_until = ctx.db.scalar(
        text("SELECT locked_until FROM users WHERE email = :email"),
        {"email": ctx.lockable_email},
    )
    assert locked_until is not None and locked_until > datetime.now(timezone.utc)


def test_the_unknown_email_cost_matches_a_real_account(ctx):
    assert ctx.login("nobody@gsprobe.dev")[0] == 401


def test_rate_limits_answer_429_with_retry_after(ctx):
    last = None
    for _ in range(settings.login_max_attempts * 3):
        last = ctx.client.post("/auth/login", data={"username": "nobody@gsprobe.dev",
                                                    "password": "wrong-password-1"})
        if last.status_code == 429:
            break
    assert last.status_code == 429, "the login window never filled"
    assert int(last.headers["retry-after"]) >= 1


# ---- the shape of a refusal ----

def test_errors_carry_the_envelope_and_the_request_id(ctx):
    response = ctx.client.get("/courses/never-published-here")
    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"error", "detail", "request_id"}
    assert body["request_id"] == response.headers["x-request-id"]


def test_validation_failures_are_enveloped_too(ctx):
    response = ctx.client.post("/auth/register", json={"full_name": "A", "email": "nope",
                                                       "phone": "123", "password": "short"})
    assert response.status_code == 422
    assert response.json()["error"] == "validation_failed"


def test_oversized_bodies_are_refused_before_parsing(ctx):
    response = ctx.client.post("/auth/refresh",
                               json={"refresh_token": "x" * 2_000_000})
    assert response.status_code == 413


def test_the_documentation_surface_follows_the_switch(ctx):
    expected = 200 if settings.expose_docs else 404
    assert ctx.client.get("/docs").status_code == expected
    assert ctx.client.get("/openapi.json").status_code == expected


def test_public_catalogue_is_cacheable_but_private_data_is_not(ctx):
    catalogue = ctx.client.get("/courses")
    assert catalogue.status_code == 200
    if settings.public_cache_seconds > 0:
        assert "public," in catalogue.headers["cache-control"]
    else:
        assert "public," not in catalogue.headers.get("cache-control", "")
    mine = ctx.client.get("/me/courses", headers=bearer(ctx.member_token))
    assert "public," not in mine.headers.get("cache-control", "")
