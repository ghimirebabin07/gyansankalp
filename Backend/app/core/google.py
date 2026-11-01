"""Google ID token verification.

The browser hands us a token that Google signed. Nothing inside it counts until
the signature checks out against Google's own keys and the audience is this
site's client id - the alternative is letting anyone POST a JSON blob claiming
any email address they like and being handed a session for it.
"""

import logging
from dataclasses import dataclass

import jwt
from jwt import PyJWKClient
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import GoogleTokenUse

log = logging.getLogger(__name__)

# Google has served tokens under both spellings of its issuer.
TRUSTED_ISSUERS = ("https://accounts.google.com", "accounts.google.com")
MAX_CLOCK_SKEW_SECONDS = 60
EMAIL_MAX_LENGTH = 255
NAME_MAX_LENGTH = 120


class GoogleTokenError(Exception):
    """The token is refused. The reason is logged, never sent to the client."""


class GoogleLoginDisabled(GoogleTokenError):
    """No client id means there is nothing to check a token's audience against."""


@dataclass(frozen=True)
class GoogleIdentity:
    subject: str
    email: str
    full_name: str
    issued_at: int


_keys: PyJWKClient | None = None


def signing_keys() -> PyJWKClient:
    """One cached key set per process; Google rotates keys about monthly."""
    global _keys
    if _keys is None:
        _keys = PyJWKClient(
            settings.google_jwks_url,
            cache_keys=True,
            lifespan=24 * 60 * 60,
            timeout=5,
        )
    return _keys


def verify_id_token(token: str) -> GoogleIdentity:
    if not settings.google_client_id:
        raise GoogleLoginDisabled("google sign-in is not configured")

    try:
        key = signing_keys().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.google_client_id,
            issuer=TRUSTED_ISSUERS,
            leeway=MAX_CLOCK_SKEW_SECONDS,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except GoogleTokenError:
        raise
    except Exception as exc:
        # The exception text can name a key id or a URL; a student does not need it.
        log.warning("rejected a google id token: %s", type(exc).__name__)
        raise GoogleTokenError("the google token was not accepted") from exc

    subject = str(claims.get("sub") or "")
    email = str(claims.get("email") or "").strip().lower()
    if not subject or not email:
        raise GoogleTokenError("token carries no subject or email address")
    if len(email) > EMAIL_MAX_LENGTH:
        raise GoogleTokenError("token email is impossibly long")
    # Missing counts as unverified: a claim we cannot check is a claim we did not get.
    if claims.get("email_verified") is not True:
        raise GoogleTokenError("google reports this address as unverified")

    name = str(claims.get("name") or "").strip() or email.split("@")[0]
    return GoogleIdentity(
        subject=subject[:32],
        email=email,
        full_name=name[:NAME_MAX_LENGTH],
        issued_at=int(claims["iat"]),
    )


def consume_once(db: Session, identity: GoogleIdentity) -> None:
    """Each Google ID token can be exchanged once, for the rest of its hour.

    Students and staff share the record on purpose: a credential spent at one sign-in
    door is spent, so a copy lifted off a browser cannot be replayed at the other.
    """
    db.add(GoogleTokenUse(sub=identity.subject, issued_at=identity.issued_at))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "That Google sign-in has already been used. Please sign in again.",
        )
