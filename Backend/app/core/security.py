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
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_refresh_token() -> tuple[str, str]:
    """Returns (raw_token_for_user, hash_to_store)."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_refresh_token(raw)