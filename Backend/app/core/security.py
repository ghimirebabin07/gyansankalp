import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt  # type: ignore
from argon2 import PasswordHasher  # type: ignore
from argon2.exceptions import VerifyMismatchError  # type: ignore 

from app.core.config import settings

ph = PasswordHasher()


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return ph.verify(hashed, password)
    except VerifyMismatchError:
        return False


def create_access_token(user_id: int, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "user",  # keeps a student token out of the admin dependency
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_admin_access_token(admin_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(admin_id),
        "type": "admin",
        "iat": now,
        "exp": now + timedelta(minutes=settings.admin_access_token_minutes),
    }
    return jwt.encode(payload, settings.admin_jwt_secret, algorithm=settings.jwt_algorithm)


def create_admin_otp_challenge(admin_id: int, otp_id: int) -> str:
    """The waiting-room pass handed to the browser between the two halves of login.

    It names the admin and the code row, and nothing else: no admin route accepts
    this type, so holding one is proof you are waiting for a code, not proof you
    are staff.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(admin_id),
        "otp": str(otp_id),
        "type": "admin_otp",
        "iat": now,
        "exp": now + timedelta(minutes=settings.admin_otp_challenge_minutes),
    }
    return jwt.encode(payload, settings.admin_jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def decode_admin_token(token: str) -> dict:
    return jwt.decode(token, settings.admin_jwt_secret, algorithms=[settings.jwt_algorithm])


def hash_token(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hash_refresh_token(raw: str) -> str:
    return hash_token(raw)


def new_refresh_token() -> tuple[str, str]:
    """Returns (raw_token_for_user, hash_to_store)."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_token(raw)


def new_verification_token() -> tuple[str, str]:
    """A shorter token than a refresh token: it travels inside a clicked link."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def new_admin_otp() -> tuple[str, str]:
    """(code for the email, hash for the database)."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    return code, hash_password(code)


def verify_admin_otp(code: str, hashed: str) -> bool:
    try:
        return ph.verify(hashed, code)
    except VerifyMismatchError:
        return False
    except Exception:
        # A corrupt hash is a refused code, not a 500 on someone's login.
        return False