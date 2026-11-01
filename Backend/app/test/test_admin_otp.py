"""Staff sign-in and role-based access, end to end through the HTTP stack.

Google is stubbed the same way the student tests stub it, and the emailed code is
captured instead of mailed. What is not stubbed is the gate: every case goes
through the real dependencies, so a route that forgot to ask for a capability
fails here rather than in production.

These tests delete rows, so they only run against a throwaway database.
"""

import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core import google, ratelimit
from app.core.config import settings
from app.core.ratelimit import SlidingWindow
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.admin import Admin, AdminRole, CourseAssignment
from app.models.course import Course, Topic
from app.models.user import User
from app.routers import admin_auth as staff

CLIENT_ID = "gyansankalp-staff-test.apps.googleusercontent.com"
CLIENT_IP = "testclient"

STAFF = {
    "super": ("boss@gsprobe.dev", "900000000001", AdminRole.super_admin),
    "manager": ("pages@gsprobe.dev", "900000000002", AdminRole.content_manager),
    "editor": ("writer@gsprobe.dev", "900000000003", AdminRole.editor),
}

TABLES = ("admin_activity_logs", "admin_otps", "admin_refresh_tokens",
          "course_assignments", "materials", "enrollments", "topics", "courses",
          "google_token_uses", "users", "admins")

signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class StubKeySource:
    """Stands in for PyJWKClient so no test reaches out to googleapis.com."""

    def get_signing_key_from_jwt(self, _token):
        return signing_key.public_key()


def google_token(**overrides) -> str:
    now = int(time.time())
    claims = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "900000000009",
        "email": "stranger@gsprobe.dev",
        "email_verified": True,
        "name": "Stranger",
        "iat": now,
        "exp": now + 3600,
    }
    claims.update(overrides)
    return jwt.encode(claims, signing_key, algorithm="RS256")


@pytest.fixture(scope="module")
def ctx():
    name = (engine.url.database or "").lower()
    if settings.app_env == "production" or not ("test" in name or name.endswith("_ci")):
        pytest.skip(f"{name!r} is not a throwaway database and these tests delete rows")

    settings.google_client_id = CLIENT_ID
    google._keys = StubKeySource()
    # The code is captured instead of mailed, the same way the student tests catch
    # their confirmation links.
    ctx_sent: list[tuple[str, str]] = []
    real_send = staff.send_otp
    staff.send_otp = lambda to, code: ctx_sent.append((to, code)) or True

    db = SessionLocal()
    try:
        yield SimpleNamespace(db=db, client=TestClient(app), sent=ctx_sent, sessions={})
    finally:
        staff.send_otp = real_send
        settings.google_client_id = None
        google._keys = None
        for table in TABLES:
            db.execute(text(f"DELETE FROM {table}"))
        db.commit()
        db.close()


@pytest.fixture(autouse=True)
def fresh_state(ctx):
    """Roster, two courses with one topic each, empty counters, no codes sent."""
    for window in vars(ratelimit).values():
        if isinstance(window, SlidingWindow):
            window.reset(CLIENT_IP)
    for table in TABLES:
        ctx.db.execute(text(f"DELETE FROM {table}"))
    ctx.db.commit()

    owned = Course(title="Assigned", slug="staff-assigned", exam_level="kharidar",
                   is_published=True)
    other = Course(title="Elsewhere", slug="staff-elsewhere", exam_level="nasu",
                   is_published=True)
    ctx.db.add_all([owned, other])
    ctx.db.commit()
    owned_topic = Topic(course_id=owned.id, title="Owned chapter", position=1)
    other_topic = Topic(course_id=other.id, title="Other chapter", position=1)
    ctx.db.add_all([owned_topic, other_topic])
    for email, _sub, role in STAFF.values():
        ctx.db.add(Admin(email=email, full_name=email.split("@")[0], role=role,
                         is_active=True,
                         # No staff login reads this column any more.
                         password_hash="unused"))
    ctx.db.commit()

    ctx.sent.clear()
    ctx.sessions.clear()
    ctx.owned_course_id = owned.id
    ctx.other_course_id = other.id
    ctx.owned_topic_id = owned_topic.id
    ctx.other_topic_id = other_topic.id
    return ctx


def staff_id(db, email: str) -> int:
    return db.scalar(select(Admin.id).where(Admin.email == email))


def assign_editor(ctx, *course_ids: int):
    editor = staff_id(ctx.db, STAFF["editor"][0])
    for course_id in course_ids:
        ctx.db.add(CourseAssignment(course_id=course_id, admin_id=editor))
    ctx.db.commit()


def begin(ctx, email: str, sub: str, *, iat: int | None = None):
    """The first half: Google proves the person, a code goes to their mailbox."""
    return ctx.client.post(
        "/admin/auth/google",
        json={"id_token": google_token(email=email, sub=sub, iat=iat or int(time.time()))},
    )


def code_sent(ctx) -> str:
    return ctx.sent[-1][1]


def verify(ctx, challenge: str, code: str):
    return ctx.client.post("/admin/auth/otp/verify",
                           json={"challenge": challenge, "code": code})


def sign_in(ctx, key: str) -> str:
    """Full sign-in for one roster account. Returns the access token."""
    email, sub, _role = STAFF[key]
    response = begin(ctx, email, sub)
    assert response.status_code == 200, response.text
    tokens = verify(ctx, response.json()["challenge"], code_sent(ctx))
    assert tokens.status_code == 200, tokens.text
    ctx.sessions[key] = tokens.json()
    return tokens.json()["access_token"]


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def live_codes(db, email: str) -> int:
    return db.scalar(text(
        "SELECT count(*) FROM admin_otps o JOIN admins a ON a.id = o.admin_id "
        "WHERE a.email = :email AND o.consumed_at IS NULL AND o.expires_at > NOW()"),
        {"email": email})


def add_student(db, email: str, phone: str):
    db.add(User(full_name="Payer", email=email, phone=phone,
                password_hash="unused", role="student", is_active=True))
    db.commit()


# ---- the two halves of staff sign-in ----

def test_a_correct_code_opens_a_session_and_can_be_used_once(ctx):
    email, sub, _ = STAFF["manager"]
    started = begin(ctx, email, sub)
    assert started.status_code == 200, started.text
    challenge = started.json()["challenge"]
    code = code_sent(ctx)

    row = ctx.db.scalar(select(Admin).where(Admin.email == email))
    assert row.google_sub == sub, "the account never got bound to Google"

    first = verify(ctx, challenge, code)
    assert first.status_code == 200, first.text
    assert len(code) == 6 and code.isdigit()
    me = ctx.client.get("/admin/auth/me", headers=bearer(first.json()["access_token"]))
    assert me.json()["role"] == "content_manager"
    assert me.json()["google_linked"] is True

    assert verify(ctx, challenge, code).status_code == 401, "a code worked twice"


def test_the_emailed_code_is_never_in_the_sign_in_response(ctx):
    email, sub, _ = STAFF["super"]
    body = begin(ctx, email, sub).json()
    assert set(body) == {"challenge", "code_expires_in", "resend_after"}
    assert body["code_expires_in"] == settings.admin_otp_minutes * 60
    assert body["resend_after"] == settings.admin_otp_resend_seconds
    assert len(ctx.sent) == 1
    assert ctx.sent[0][0] == email, "a code went to the wrong mailbox"
    assert not any(code in str(body) for _to, code in ctx.sent)


def test_a_challenge_token_opens_no_admin_route(ctx):
    email, sub, _ = STAFF["editor"]
    challenge = begin(ctx, email, sub).json()["challenge"]
    # It is signed with the admin key and names a real admin, and it still means
    # nothing to the panel: the type claim is not "admin".
    assert ctx.client.get("/admin/courses", headers=bearer(challenge)).status_code == 403
    assert ctx.client.get("/admin/auth/me", headers=bearer(challenge)).status_code == 403


def test_an_address_that_is_not_on_the_staff_list_is_refused(ctx):
    response = begin(ctx, "whoever@gsprobe.dev", "900000000099")
    assert response.status_code == 403
    assert ctx.sent == [], "a code was mailed to an address nobody approved"
    assert ctx.db.scalar(text("SELECT count(*) FROM admins")) == 3, "a staff row was created"


def test_a_deactivated_account_cannot_start_a_sign_in(ctx):
    email, sub, _ = STAFF["editor"]
    ctx.db.execute(text("UPDATE admins SET is_active = false WHERE email = :e"), {"e": email})
    ctx.db.commit()
    assert begin(ctx, email, sub).status_code == 403
    assert ctx.sent == []


def test_a_bound_account_refuses_a_different_google_subject(ctx):
    email = STAFF["manager"][0]
    assert begin(ctx, email, "900000000002").status_code == 200
    assert begin(ctx, email, "900000000055").status_code == 403, "the address was claimed twice"


def test_wrong_codes_are_counted_and_the_code_is_burned(ctx):
    email, sub, _ = STAFF["super"]
    challenge = begin(ctx, email, sub).json()["challenge"]
    code = code_sent(ctx)
    wrong = "000000" if code != "000000" else "111111"

    for _ in range(settings.admin_otp_max_attempts):
        assert verify(ctx, challenge, wrong).status_code == 401

    # The right code, after the attempts ran out: the code is gone, not the mailbox.
    assert verify(ctx, challenge, code).status_code == 401
    assert live_codes(ctx.db, email) == 0


def test_an_expired_code_is_refused(ctx):
    email, sub, _ = STAFF["super"]
    challenge = begin(ctx, email, sub).json()["challenge"]
    code = code_sent(ctx)
    ctx.db.execute(text("UPDATE admin_otps SET expires_at = NOW() - INTERVAL '1 minute'"))
    ctx.db.commit()
    assert verify(ctx, challenge, code).status_code == 401


def test_resending_waits_out_the_cooldown_and_replaces_the_code(ctx):
    email, sub, _ = STAFF["super"]
    challenge = begin(ctx, email, sub).json()["challenge"]
    first_code = code_sent(ctx)

    soon = ctx.client.post("/admin/auth/otp/resend", json={"challenge": challenge})
    assert soon.status_code == 429
    assert int(soon.headers["retry-after"]) >= 1
    assert len(ctx.sent) == 1, "the cooldown still mailed a second code"

    ctx.db.execute(text("UPDATE admin_otps SET created_at = created_at - INTERVAL '10 minutes'"))
    ctx.db.commit()
    assert ctx.client.post("/admin/auth/otp/resend",
                           json={"challenge": challenge}).status_code == 202
    assert len(ctx.sent) == 2
    assert code_sent(ctx) != first_code
    assert verify(ctx, challenge, first_code).status_code == 401, "the retired code still worked"
    assert verify(ctx, challenge, code_sent(ctx)).status_code == 200


def test_a_code_that_cannot_be_mailed_refuses_the_login(ctx, monkeypatch):
    monkeypatch.setattr(staff, "send_otp", lambda to, code: False)
    assert begin(ctx, STAFF["manager"][0], STAFF["manager"][1]).status_code == 503
    assert live_codes(ctx.db, STAFF["manager"][0]) == 0, "a half login was left waiting"


def test_a_captured_google_token_cannot_be_exchanged_twice(ctx):
    email, sub, _ = STAFF["manager"]
    token = google_token(email=email, sub=sub)
    assert ctx.client.post("/admin/auth/google", json={"id_token": token}).status_code == 200
    assert ctx.client.post("/admin/auth/google", json={"id_token": token}).status_code == 401


def test_a_forged_google_token_never_reaches_the_mailer(ctx):
    foreign_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    email, sub, _ = STAFF["super"]
    forged = jwt.encode(
        {"iss": "https://accounts.google.com", "aud": CLIENT_ID, "sub": sub,
         "email": email, "email_verified": True,
         "iat": int(time.time()), "exp": int(time.time()) + 600},
        foreign_key, algorithm="RS256")
    assert ctx.client.post("/admin/auth/google", json={"id_token": forged}).status_code == 401
    assert ctx.sent == []


# ---- the session itself ----

def test_the_session_renews_once_and_logout_ends_it(ctx):
    sign_in(ctx, "super")
    refresh = ctx.sessions["super"]["refresh_token"]

    renewed = ctx.client.post("/admin/auth/refresh", json={"refresh_token": refresh})
    assert renewed.status_code == 200
    assert ctx.client.post("/admin/auth/refresh",
                           json={"refresh_token": refresh}).status_code == 401

    second = renewed.json()["refresh_token"]
    assert ctx.client.post("/admin/auth/logout", json={"refresh_token": second}).status_code == 204
    assert ctx.client.post("/admin/auth/refresh",
                           json={"refresh_token": second}).status_code == 401


def test_a_role_change_ends_the_existing_session(ctx):
    editor_token = sign_in(ctx, "editor")
    editor_refresh = ctx.sessions["editor"]["refresh_token"]
    assert ctx.client.get("/admin/courses", headers=bearer(editor_token)).status_code == 200

    super_token = sign_in(ctx, "super")
    changed = ctx.client.patch(f"/admin/staff/{staff_id(ctx.db, STAFF['editor'][0])}",
                               json={"role": "content_manager"},
                               headers=bearer(super_token))
    assert changed.status_code == 200, changed.text

    # The editor can now manage enrollments, which the role grants, so the proof of
    # revocation is the refresh token: it was burned when the role was written.
    assert ctx.client.post("/admin/auth/refresh",
                           json={"refresh_token": editor_refresh}).status_code == 401


def test_deactivation_blocks_the_next_request(ctx):
    manager_token = sign_in(ctx, "manager")
    super_token = sign_in(ctx, "super")
    revoked = ctx.client.patch(f"/admin/staff/{staff_id(ctx.db, STAFF['manager'][0])}",
                               json={"is_active": False}, headers=bearer(super_token))
    assert revoked.status_code == 200, revoked.text
    assert ctx.client.get("/admin/courses", headers=bearer(manager_token)).status_code == 401
    assert ctx.client.post("/admin/auth/refresh",
                           json={"refresh_token": ctx.sessions["manager"]["refresh_token"]}
                           ).status_code == 401


# ---- role-based access ----

def test_an_editor_sees_only_assigned_courses(ctx):
    token = sign_in(ctx, "editor")
    assign_editor(ctx, ctx.owned_course_id)

    listing = ctx.client.get("/admin/courses", headers=bearer(token))
    assert listing.status_code == 200
    assert [row["id"] for row in listing.json()] == [ctx.owned_course_id]
    assert ctx.client.get(f"/admin/topics/{ctx.owned_topic_id}/materials",
                          headers=bearer(token)).status_code == 200
    assert ctx.client.get(f"/admin/topics/{ctx.other_topic_id}/materials",
                          headers=bearer(token)).status_code == 403


def test_an_editor_edits_assigned_content_only(ctx):
    token = sign_in(ctx, "editor")
    assign_editor(ctx, ctx.owned_course_id)

    allowed = ctx.client.post(f"/admin/courses/{ctx.owned_course_id}/topics",
                              json={"title": "New chapter", "position": 2},
                              headers=bearer(token))
    assert allowed.status_code == 201, allowed.text

    refused = ctx.client.post(f"/admin/courses/{ctx.other_course_id}/topics",
                              json={"title": "Not yours", "position": 1},
                              headers=bearer(token))
    assert refused.status_code == 403
    assert refused.json()["error"], "a refusal must still be a shaped error"
    assert ctx.client.patch(f"/admin/topics/{ctx.other_topic_id}",
                            json={"title": "Rewritten"},
                            headers=bearer(token)).status_code == 403


def test_an_editor_without_assignments_edits_nothing(ctx):
    token = sign_in(ctx, "editor")
    assert ctx.client.get("/admin/courses", headers=bearer(token)).json() == []
    assert ctx.client.patch(f"/admin/courses/{ctx.owned_course_id}",
                            json={"title": "Nobody assigned me"},
                            headers=bearer(token)).status_code == 403


def test_an_editor_cannot_create_or_delete_a_course(ctx):
    token = sign_in(ctx, "editor")
    assign_editor(ctx, ctx.owned_course_id)

    created = ctx.client.post("/admin/courses",
                              json={"title": "Sneak in", "slug": "staff-sneak-in",
                                    "exam_level": "kharidar"},
                              headers=bearer(token))
    assert created.status_code == 403
    assert ctx.client.delete(f"/admin/courses/{ctx.owned_course_id}",
                             headers=bearer(token)).status_code == 403
    assert ctx.db.scalar(text("SELECT count(*) FROM courses")) == 2


def test_an_editor_cannot_touch_student_access(ctx):
    token = sign_in(ctx, "editor")
    assign_editor(ctx, ctx.owned_course_id)
    add_student(ctx.db, "payer@gsprobe.dev", "9812345678")

    refused = ctx.client.post("/admin/enrollments",
                              json={"email": "payer@gsprobe.dev",
                                    "course_id": ctx.owned_course_id},
                              headers=bearer(token))
    assert refused.status_code == 403
    assert ctx.db.scalar(text("SELECT count(*) FROM enrollments")) == 0
    assert ctx.client.get("/admin/enrollments", headers=bearer(token)).status_code == 403


def test_a_content_manager_runs_content_and_access_but_not_staff(ctx):
    token = sign_in(ctx, "manager")
    add_student(ctx.db, "payer2@gsprobe.dev", "9812345679")

    assert ctx.client.post("/admin/courses",
                           json={"title": "Managed", "slug": "staff-managed",
                                 "exam_level": "kharidar"},
                           headers=bearer(token)).status_code == 201
    assert ctx.client.post("/admin/enrollments",
                           json={"email": "payer2@gsprobe.dev",
                                 "course_id": ctx.owned_course_id},
                           headers=bearer(token)).status_code == 201
    # Not limited by course assignment: a manager works on the whole catalogue.
    assert ctx.client.patch(f"/admin/courses/{ctx.other_course_id}",
                            json={"title": "Renamed elsewhere"},
                            headers=bearer(token)).status_code == 200
    assert ctx.client.get("/admin/staff", headers=bearer(token)).status_code == 403
    assert ctx.client.post("/admin/staff",
                           json={"full_name": "Extra", "email": "extra@gsprobe.dev",
                                 "role": "editor"},
                           headers=bearer(token)).status_code == 403


def test_only_a_super_admin_manages_staff(ctx):
    token = sign_in(ctx, "super")
    created = ctx.client.post("/admin/staff",
                              json={"full_name": "Fourth Editor",
                                    "email": "fourth@gsprobe.dev", "role": "editor"},
                              headers=bearer(token))
    assert created.status_code == 201, created.text
    assert created.json()["google_linked"] is False
    assert len(ctx.client.get("/admin/staff", headers=bearer(token)).json()) == 4

    # Nothing here is reachable without a Super Admin session, so there is no
    # public staff registration to find.
    assert ctx.client.get("/admin/staff").status_code == 401
    assert ctx.client.post("/admin/staff",
                           json={"full_name": "Intruder", "email": "intruder@gsprobe.dev",
                                 "role": "super_admin"}).status_code == 401


def test_the_last_active_super_admin_cannot_be_removed(ctx):
    token = sign_in(ctx, "super")
    me = staff_id(ctx.db, STAFF["super"][0])

    assert ctx.client.patch(f"/admin/staff/{me}", json={"role": "editor"},
                            headers=bearer(token)).status_code == 409
    assert ctx.client.patch(f"/admin/staff/{me}", json={"is_active": False},
                            headers=bearer(token)).status_code == 409
    assert ctx.db.scalar(text("SELECT role FROM admins WHERE id = :i"),
                         {"i": me}) == "super_admin"

    # A second Super Admin makes stepping down possible for someone else.
    other = ctx.client.post("/admin/staff",
                            json={"full_name": "Second Boss", "email": "second@gsprobe.dev",
                                  "role": "super_admin"},
                            headers=bearer(token)).json()["id"]
    assert ctx.client.patch(f"/admin/staff/{other}", json={"role": "editor"},
                            headers=bearer(token)).status_code == 200
    assert ctx.client.patch(f"/admin/staff/{me}", json={"is_active": False},
                            headers=bearer(token)).status_code == 409


def test_a_super_admin_cannot_deactivate_themselves(ctx):
    token = sign_in(ctx, "super")
    me = staff_id(ctx.db, STAFF["super"][0])
    ctx.client.post("/admin/staff", json={"full_name": "Second Boss",
                                         "email": "second2@gsprobe.dev",
                                         "role": "super_admin"},
                    headers=bearer(token))
    # Two active Super Admins now, so only the self-deactivation rule can stop this.
    assert ctx.client.patch(f"/admin/staff/{me}", json={"is_active": False},
                            headers=bearer(token)).status_code == 409


def test_changing_an_email_unbinds_the_google_account(ctx):
    token = sign_in(ctx, "super")
    email, sub, _ = STAFF["editor"]
    ctx.db.execute(text("UPDATE admins SET google_sub = :s WHERE email = :e"),
                   {"s": sub, "e": email})
    ctx.db.commit()

    changed = ctx.client.patch(f"/admin/staff/{staff_id(ctx.db, email)}",
                               json={"email": "writer.new@gsprobe.dev"},
                               headers=bearer(token))
    assert changed.status_code == 200, changed.text
    assert changed.json()["google_linked"] is False

    # The row no longer answers to the address it was made for, and the new address
    # binds itself on that person's first sign-in.
    assert begin(ctx, email, sub).status_code == 403
    assert begin(ctx, "writer.new@gsprobe.dev", "900000000077").status_code == 200


def test_duplicate_staff_emails_are_refused(ctx):
    token = sign_in(ctx, "super")
    body = {"full_name": "Copy Cat", "email": STAFF["manager"][0], "role": "editor"}
    assert ctx.client.post("/admin/staff", json=body, headers=bearer(token)).status_code == 409
    assert ctx.client.patch(f"/admin/staff/{staff_id(ctx.db, STAFF['editor'][0])}",
                            json={"email": STAFF["manager"][0]},
                            headers=bearer(token)).status_code == 409


def test_courses_are_assigned_to_an_editor_in_one_set(ctx):
    token = sign_in(ctx, "super")
    target = staff_id(ctx.db, STAFF["editor"][0])
    path = f"/admin/staff/{target}/courses"

    both = ctx.client.put(path, json={"course_ids": [ctx.owned_course_id, ctx.other_course_id]},
                          headers=bearer(token))
    assert both.status_code == 200
    assert sorted(both.json()) == sorted([ctx.owned_course_id, ctx.other_course_id])

    replaced = ctx.client.put(path, json={"course_ids": [ctx.owned_course_id]},
                              headers=bearer(token))
    assert replaced.json() == [ctx.owned_course_id]
    assert ctx.client.get(path, headers=bearer(token)).json() == [ctx.owned_course_id]

    assert ctx.client.put(path, json={"course_ids": [4242]},
                          headers=bearer(token)).status_code == 404


# ---- the activity record ----

def test_staff_actions_leave_a_record(ctx):
    super_token = sign_in(ctx, "super")
    editor_token = sign_in(ctx, "editor")
    assign_editor(ctx, ctx.owned_course_id)

    ctx.client.patch(f"/admin/courses/{ctx.owned_course_id}", json={"title": "Retitled"},
                     headers=bearer(editor_token))
    ctx.client.patch(f"/admin/staff/{staff_id(ctx.db, STAFF['manager'][0])}",
                     json={"role": "editor"}, headers=bearer(super_token))

    actions = [row[0] for row in ctx.db.execute(
        text("SELECT action FROM admin_activity_logs ORDER BY id")).all()]
    assert "staff.login" in actions, actions
    assert "course.updated" in actions
    assert "staff.updated" in actions

    editor_rows = ctx.db.scalar(text(
        "SELECT count(*) FROM admin_activity_logs a JOIN admins s ON s.id = a.admin_id "
        "WHERE s.email = :e"), {"e": STAFF["editor"][0]})
    assert editor_rows >= 2, "an editor's own actions were not attributed to them"

    # A row is written against whoever did it, so the panel can read one person's
    # history back - including that someone changed their role.
    boss = staff_id(ctx.db, STAFF["super"][0])
    seen = ctx.client.get(f"/admin/staff/{boss}/activity", headers=bearer(super_token))
    assert seen.status_code == 200
    assert any(row["action"] == "staff.updated" for row in seen.json())
    manager = staff_id(ctx.db, STAFF["manager"][0])
    theirs = ctx.client.get(f"/admin/staff/{manager}/activity", headers=bearer(super_token))
    assert [row["action"] for row in theirs.json()] == []

    editor = staff_id(ctx.db, STAFF["editor"][0])
    own = ctx.client.get(f"/admin/staff/{editor}/activity", headers=bearer(super_token))
    assert [row["action"] for row in own.json()] == [
        "course.updated", "staff.login", "staff.code_sent",
    ], "the log should read newest first"
