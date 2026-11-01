"""Google sign-in and email confirmation, tested without touching Google.

Tokens are signed here with a throwaway RSA key and the key lookup is replaced by
a stub, so the tests walk the same verification path that runs against Google's
real keys - including the cases that must be refused.

These tests delete rows, so they only run against a throwaway database.
"""

import time
from itertools import count
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

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
from app.models.course import Course
from app.models.user import User
from app.routers import auth as auth_router

CLIENT_ID = "gyansankalp-test.apps.googleusercontent.com"
PASSWORD = "Str0ng-Passw0rd-for-tests"
CLIENT_IP = "testclient"
phone_counter = count(1)
TABLES = ("access_logs", "materials", "refresh_tokens", "enrollments",
          "google_token_uses", "users", "admins", "topics", "courses")

signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
foreign_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class StubKeySource:
    """Stands in for PyJWKClient so no test reaches out to googleapis.com."""

    def get_signing_key_from_jwt(self, _token):
        return signing_key.public_key()


def google_token(**overrides) -> str:
    """A Google-shaped ID token, signed by the key the stub advertises."""
    now = int(time.time())
    claims = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "112233445566",
        "email": "new.student@gsprobe.dev",
        "email_verified": True,
        "name": "New Student",
        "iat": now,
        "exp": now + 3600,
    }
    claims.update(overrides)
    key = claims.pop("signing_key", signing_key)
    for name, value in list(claims.items()):
        if value is None:
            del claims[name]
    return jwt.encode(claims, key, algorithm="RS256")


@pytest.fixture(scope="module")
def ctx():
    name = (engine.url.database or "").lower()
    if settings.app_env == "production" or not ("test" in name or name.endswith("_ci")):
        pytest.skip(f"{name!r} is not a throwaway database and these tests delete rows")

    settings.google_client_id = CLIENT_ID
    google._keys = StubKeySource()

    db = SessionLocal()
    try:
        for table in TABLES:
            db.execute(text(f"DELETE FROM {table}"))
        db.commit()
        course = Course(title="Confirmed Only", slug="google-confirmed-course",
                        exam_level="kharidar", price_npr=0, is_published=True)
        db.add(course)
        db.commit()
        yield SimpleNamespace(db=db, client=TestClient(app), course_id=course.id)
    finally:
        settings.google_client_id = None
        google._keys = None
        for table in TABLES:
            db.execute(text(f"DELETE FROM {table}"))
        db.commit()
        db.close()


@pytest.fixture(autouse=True)
def clean_state(ctx, sent_links):
    for window in vars(ratelimit).values():
        if isinstance(window, SlidingWindow):
            window.reset(CLIENT_IP)
    for table in ("google_token_uses", "enrollments", "refresh_tokens", "users"):
        ctx.db.execute(text(f"DELETE FROM {table}"))
    ctx.db.commit()
    ctx.sent = sent_links
    return ctx


@pytest.fixture
def sent_links(monkeypatch):
    """Verification links are captured here instead of being emailed."""
    captured: list[str] = []
    monkeypatch.setattr(auth_router, "send_verification",
                        lambda to, url: captured.append(url) or True)
    return captured


def sign_in_with_google(ctx, **claims):
    return ctx.client.post("/auth/google", json={"id_token": google_token(**claims)})


def make_password_account(ctx, email: str) -> str:
    """Register and sign in by password; returns the link token, still unconfirmed."""
    phone = f"98{next(phone_counter):08d}"
    created = ctx.client.post("/auth/register", json={
        "full_name": "Password Student", "email": email,
        "phone": phone, "password": PASSWORD,
    })
    assert created.status_code == 201, created.text
    signed_in = ctx.client.post("/auth/login",
                                data={"username": email, "password": PASSWORD})
    assert signed_in.status_code == 200, signed_in.text
    ctx.access_token = signed_in.json()["access_token"]
    return parse_qs(urlparse(ctx.sent[-1]).query)["token"][0]


def confirm(ctx, token: str):
    return ctx.client.post("/auth/verify-email", json={"token": token})


def user_row(ctx, email: str) -> User:
    return ctx.db.scalar(select(User).where(User.email == email))


# ---- a Google identity creates a student ----

def test_google_sign_in_creates_a_student_without_a_phone(ctx):
    response = sign_in_with_google(ctx)
    assert response.status_code == 200, response.text
    assert response.json()["created"] is True
    user = user_row(ctx, "new.student@gsprobe.dev")
    assert user is not None and user.phone is None
    assert user.google_sub == "112233445566"
    # Google proved the address, so there is nothing left to confirm.
    assert user.email_verified_at is not None


def test_signing_in_again_reports_an_account_that_already_existed(ctx):
    """The register page needs to know it walked into someone else's door."""
    sign_in_with_google(ctx, sub="700000000011", email="already.there@gsprobe.dev")
    again = sign_in_with_google(ctx, sub="700000000011", email="already.there@gsprobe.dev",
                               iat=int(time.time()) - 5)
    assert again.status_code == 200, again.text
    assert again.json()["created"] is False


def test_the_same_google_identity_returns_to_the_same_student(ctx):
    first = sign_in_with_google(ctx, sub="700000000001")
    assert first.status_code == 200
    second = sign_in_with_google(ctx, sub="700000000001", iat=int(time.time()) - 5)
    assert second.status_code == 200
    # A fresh session each time, for the same student id.
    assert first.json()["refresh_token"] != second.json()["refresh_token"]

    def student_id(access_token: str) -> str:
        claims = jwt.decode(access_token, settings.jwt_secret, algorithms=["HS256"])
        return claims["sub"]

    assert student_id(first.json()["access_token"]) == student_id(second.json()["access_token"])
    rows = ctx.db.scalar(text("SELECT count(*) FROM users WHERE google_sub = :sub"),
                         {"sub": "700000000001"})
    assert rows == 1, "a repeat sign-in created a second account"


def test_google_students_are_confirmed_enough_to_enroll(ctx):
    tokens = sign_in_with_google(ctx).json()
    enrolled = ctx.client.post(f"/enrollments?course_id={ctx.course_id}",
                               headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert enrolled.status_code == 201, enrolled.text


def test_a_password_chosen_at_google_signup_opens_the_typed_email_door(ctx):
    response = ctx.client.post("/auth/google", json={
        "id_token": google_token(sub="700000000012", email="pw.at.signup@gsprobe.dev"),
        "password": "Chosen-By-Student-1",
    })
    assert response.status_code == 200, response.text
    assert response.json()["created"] is True
    login = ctx.client.post("/auth/login", data={
        "username": "pw.at.signup@gsprobe.dev", "password": "Chosen-By-Student-1"})
    assert login.status_code == 200, login.text


def test_google_signin_never_replaces_a_password_the_student_already_chose(ctx):
    make_password_account(ctx, "keep.mine@gsprobe.dev")
    response = ctx.client.post("/auth/google", json={
        "id_token": google_token(sub="700000000013", email="keep.mine@gsprobe.dev"),
        "password": "Trying-To-Overwrite-1",
    })
    assert response.status_code == 200, response.text
    assert response.json()["created"] is False
    overwritten = ctx.client.post("/auth/login", data={
        "username": "keep.mine@gsprobe.dev", "password": "Trying-To-Overwrite-1"})
    assert overwritten.status_code == 401, "a google sign-in changed someone's password"
    original = ctx.client.post("/auth/login", data={
        "username": "keep.mine@gsprobe.dev", "password": PASSWORD})
    assert original.status_code == 200, original.text


def test_a_deactivated_student_cannot_sign_in_with_google(ctx):
    sign_in_with_google(ctx, sub="700000000009", email="gone@gsprobe.dev")
    ctx.db.execute(text("UPDATE users SET is_active = false WHERE email = 'gone@gsprobe.dev'"))
    ctx.db.commit()
    response = sign_in_with_google(ctx, sub="700000000009", email="gone@gsprobe.dev",
                                   iat=int(time.time()) - 30)
    assert response.status_code == 401


# ---- what must never be accepted ----

@pytest.mark.parametrize("reason,claims", [
    ("issued for a different app", {"aud": "someone-else.apps.googleusercontent.com"}),
    ("issued by an unexpected issuer", {"iss": "https://accounts.evil.example"}),
    ("expired", {"exp": int(time.time()) - 120}),
    ("address not verified at google", {"email_verified": False}),
    ("no email address at all", {"email": None}),
    ("signed by a foreign key", {"signing_key": foreign_key}),
])
def test_a_token_that_fails_verification_opens_nothing(ctx, reason, claims):
    response = sign_in_with_google(ctx, **claims)
    assert response.status_code == 401, f"accepted a token {reason}"
    assert ctx.db.scalar(text("SELECT count(*) FROM users")) == 0, f"created a user {reason}"


def test_a_captured_google_token_cannot_be_exchanged_twice(ctx):
    token = google_token(sub="700000000007")
    assert ctx.client.post("/auth/google", json={"id_token": token}).status_code == 200
    replay = ctx.client.post("/auth/google", json={"id_token": token})
    assert replay.status_code == 401
    assert replay.json()["error"], "a refusal must still be a shaped error"


def test_google_sign_in_is_refused_without_a_client_id(ctx, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", None)
    response = ctx.client.post("/auth/google", json={"id_token": google_token()})
    assert response.status_code == 503
    # Nothing was written for a request that could not be checked.
    assert ctx.db.scalar(text("SELECT count(*) FROM google_token_uses")) == 0
    assert ctx.db.scalar(text("SELECT count(*) FROM users")) == 0


# ---- the link between a Google identity and an existing account ----

def test_google_links_to_an_account_that_confirmed_its_address(ctx):
    token = make_password_account(ctx, "confirmed.first@gsprobe.dev")
    assert confirm(ctx, token).status_code == 200

    response = sign_in_with_google(ctx, email="confirmed.first@gsprobe.dev",
                                   sub="700000000002")
    assert response.status_code == 200, response.text
    user = user_row(ctx, "confirmed.first@gsprobe.dev")
    assert user.google_sub == "700000000002", "google created a second account"


def test_google_takes_over_an_account_that_never_confirmed_its_address(ctx):
    make_password_account(ctx, "unconfirmed.first@gsprobe.dev")
    response = sign_in_with_google(ctx, email="unconfirmed.first@gsprobe.dev",
                                   sub="700000000003")
    assert response.status_code == 200, response.text
    assert response.json()["created"] is False, "an existing account was reported as new"
    user = user_row(ctx, "unconfirmed.first@gsprobe.dev")
    assert user.google_sub == "700000000003", "google created a second account"
    # Google proved the mailbox, so the link nobody clicked is no longer needed.
    assert user.email_verified_at is not None
    enrolled = ctx.client.post(
        f"/enrollments?course_id={ctx.course_id}",
        headers={"Authorization": f"Bearer {response.json()['access_token']}"})
    assert enrolled.status_code == 201, enrolled.text


def test_one_account_holds_at_most_one_google_identity(ctx):
    sign_in_with_google(ctx, email="single.link@gsprobe.dev", sub="700000000004")
    second = sign_in_with_google(ctx, email="single.link@gsprobe.dev", sub="700000000005")
    assert second.status_code == 409


# ---- email confirmation ----

def test_an_unconfirmed_account_cannot_enroll_until_it_clicks_the_link(ctx):
    token = make_password_account(ctx, "later.enroller@gsprobe.dev")
    blocked = ctx.client.post(f"/enrollments?course_id={ctx.course_id}",
                              headers={"Authorization": f"Bearer {ctx.access_token}"})
    assert blocked.status_code == 403

    assert confirm(ctx, token).status_code == 200
    after = ctx.client.post(f"/enrollments?course_id={ctx.course_id}",
                            headers={"Authorization": f"Bearer {ctx.access_token}"})
    assert after.status_code == 201, after.text


def test_a_confirmation_link_works_once(ctx):
    token = make_password_account(ctx, "one.click@gsprobe.dev")
    assert confirm(ctx, token).status_code == 200
    assert confirm(ctx, token).status_code == 400


def test_an_expired_confirmation_link_is_refused(ctx):
    token = make_password_account(ctx, "stale.link@gsprobe.dev")
    ctx.db.execute(
        text("UPDATE users SET email_verify_expires_at = NOW() - INTERVAL '1 minute' "
             "WHERE email = :email"),
        {"email": "stale.link@gsprobe.dev"},
    )
    ctx.db.commit()
    assert confirm(ctx, token).status_code == 400


def test_a_fabricated_confirmation_token_is_refused(ctx):
    make_password_account(ctx, "safe.address@gsprobe.dev")
    assert confirm(ctx, "x" * 43).status_code == 400
    assert user_row(ctx, "safe.address@gsprobe.dev").email_verified_at is None


def test_resend_does_not_reveal_whether_an_address_is_registered(ctx):
    make_password_account(ctx, "known.address@gsprobe.dev")
    known = ctx.client.post("/auth/resend-verification",
                            json={"email": "known.address@gsprobe.dev"})
    unknown = ctx.client.post("/auth/resend-verification",
                              json={"email": "nobody.at.all@gsprobe.dev"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
