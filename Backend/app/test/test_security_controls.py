"""Controls that can be proven without a database.

The suites that exercise authorization through HTTP delete rows, so they only run
against a throwaway schema. These do not: each one asserts on a guard that has to
hold wherever the code runs, which is what makes them usable as a release gate.

They exist because "it is implemented" and "it holds" are different claims - the
first version of the forwarded-header rule below passed review and then failed
twelve live requests.
"""

import asyncio
from types import SimpleNamespace

import pytest
from PIL import Image
from starlette.datastructures import Headers

from app.core.config import settings
from app.core.headers import SECURITY_HEADERS, SecurityMiddleware
from app.core.ratelimit import SlidingWindow, client_ip
from app.core.security import (
    create_access_token,
    create_admin_access_token,
    create_admin_otp_challenge,
    decode_access_token,
    decode_admin_token,
    hash_password,
    new_admin_otp,
    new_refresh_token,
    verify_admin_otp,
    verify_password,
)
from app.core.watermark import stamp
from app.routers.materials import NO_STORE

LIMIT = 100


def request_with(**headers):
    # Keyword arguments cannot spell a hyphen, so underscores stand in for them.
    raw = [(key.lower().replace("_", "-").encode(), value.encode())
           for key, value in headers.items()]
    return SimpleNamespace(headers=Headers(raw=raw), client=SimpleNamespace(host="203.0.113.2"))


def test_forwarded_for_uses_the_hop_the_proxy_wrote(monkeypatch):
    """A visitor must not choose which bucket they are counted in.

    Reading the first hop made every limiter bypassable by rotating
    X-Forwarded-For, which was confirmed against the deployed API.
    """
    monkeypatch.setattr(settings, "trust_forwarded_for", True)
    assert client_ip(request_with(x_forwarded_for="1.2.3.4, 5.6.7.8")) == "5.6.7.8"
    assert client_ip(request_with(x_forwarded_for="9.9.9.9")) == "9.9.9.9"
    assert client_ip(request_with()) == "203.0.113.2"
    # An empty or whitespace list is not an identity.
    assert client_ip(request_with(x_forwarded_for="   ")) == "203.0.113.2"


def test_forgeries_do_not_bypass_the_window(monkeypatch):
    """Twenty requests wearing twenty addresses still count as one client."""
    monkeypatch.setattr(settings, "trust_forwarded_for", True)
    window = SlidingWindow("test", 3, 60)
    waits = [
        window.hit(client_ip(request_with(x_forwarded_for=f"203.0.113.{n}, 8.8.8.8")))
        for n in range(20)
    ]
    assert waits[:3] == [0, 0, 0]
    assert all(wait > 0 for wait in waits[3:])


def test_a_direct_server_ignores_the_header_entirely(monkeypatch):
    """Without a proxy in front, X-Forwarded-For is just a claim."""
    monkeypatch.setattr(settings, "trust_forwarded_for", False)
    assert client_ip(request_with(x_forwarded_for="1.2.3.4")) == "203.0.113.2"


def test_student_and_admin_keys_are_not_interchangeable():
    """Each token type is only readable by the decoder that guards its routes."""
    student = create_access_token(7, "student")
    admin = create_admin_access_token(7)

    assert decode_access_token(student)["type"] == "user"
    assert decode_admin_token(admin)["type"] == "admin"
    with pytest.raises(Exception):
        decode_admin_token(student)
    with pytest.raises(Exception):
        decode_access_token(admin)


def test_no_route_can_accept_a_sign_in_challenge_as_a_session():
    """The waiting-room pass names an admin but unlocks nothing."""
    payload = decode_admin_token(create_admin_otp_challenge(3, 42))
    assert payload["type"] == "admin_otp"
    assert payload["type"] != "admin"


def test_staff_codes_are_random_hashed_and_never_stored_plain():
    drawn = {new_admin_otp() for _ in range(50)}
    codes = {code for code, _ in drawn}
    assert len(codes) > 45  # six digits, essentially no repeats
    code, hashed = next(iter(drawn))
    assert len(code) == 6 and code.isdigit()
    assert hashed.startswith("$argon2") and code not in hashed
    assert verify_admin_otp(code, hashed)
    assert not verify_admin_otp(f"{(int(code) + 1) % 1_000_000:06d}", hashed)
    # A corrupt hash refuses the code instead of raising on someone's login.
    assert not verify_admin_otp(code, "not-a-hash")


def test_refresh_tokens_are_unpredictable_and_stored_only_as_digests():
    raws = {new_refresh_token()[0] for _ in range(100)}
    assert len(raws) == 100
    raw, digest = new_refresh_token()
    assert len(raw) >= 48 and digest != raw and len(digest) == 64


def test_password_storage_is_argon2_and_verifies():
    hashed = hash_password("Str0ng-Passw0rd")
    assert hashed.startswith("$argon2")
    assert verify_password("Str0ng-Passw0rd", hashed)
    assert not verify_password("Str0ng-Passw0rd ", hashed)


def test_page_images_are_never_cacheable():
    """Each image carries one student's identity, so a shared cache would leak it."""
    assert "no-store" in NO_STORE["Cache-Control"]
    assert "public" not in NO_STORE["Cache-Control"]
    assert NO_STORE["X-Content-Type-Options"] == "nosniff"
    assert SECURITY_HEADERS["X-Frame-Options"] == "DENY"


def test_the_watermark_lands_on_the_page():
    page = stamp(
        Image.new("RGB", (300, 400), "white"),
        "9800000000  ID42",
        "9800000000 | ID42 | 2026-11-06 12:00 UTC",
    )
    assert page.size == (300, 400)
    # A blank page is one flat colour; the stamp has to put ink somewhere on it.
    assert len(page.getcolors(maxcolors=1 << 24)) > 1


@pytest.mark.parametrize(
    "content_type, declared, expect_reject",
    [
        ("application/json", str(LIMIT + 1), True),
        ("application/json", str(LIMIT - 1), False),
        # Uploads are bounded by the route against max_upload_mb, not by this.
        ("multipart/form-data", "999999999", False),
    ],
)
def test_oversized_bodies_are_refused_before_the_route_runs(content_type, declared, expect_reject):
    sent, reached = [], [False]

    async def app(_scope, _receive, send):
        reached[0] = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/x",
        "headers": [(b"content-type", content_type.encode()),
                    (b"content-length", declared.encode())],
    }
    asyncio.run(SecurityMiddleware(app, max_body_bytes=LIMIT)(scope, receive, send))
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    assert (status == 413) == expect_reject
    assert reached[0] == (not expect_reject)
