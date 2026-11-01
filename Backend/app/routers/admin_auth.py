"""Staff sign-in: Google proves the person, an emailed code proves the mailbox.

There is no password in this router on purpose. The staff list is three Gmail
accounts, so the only credentials worth having are the one Google checks for us
and something an attacker would additionally have to steal - the inbox.

A sign-in is finished in two calls. The first hands back a waiting-room pass that
opens no admin route; the second trades that pass plus the code for a real session.
"""

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.audit import record
from app.core.config import settings
from app.core.deps import get_current_admin
from app.core.google import (
    GoogleLoginDisabled,
    GoogleTokenError,
    consume_once,
    verify_id_token,
)
from app.core.mail import send_otp
from app.core.ratelimit import admin_google
from app.core.ratelimit import admin_otp_resend
from app.core.ratelimit import admin_otp_verify
from app.core.ratelimit import admin_refresh as admin_refresh_window
from app.core.ratelimit import client_ip, limit
from app.core.security import (
    create_admin_access_token,
    create_admin_otp_challenge,
    decode_admin_token,
    hash_token,
    new_admin_otp,
    new_refresh_token,
    verify_admin_otp,
)
from app.db.session import get_db
from app.models.admin import Admin, AdminOtp, AdminRefreshToken
from app.schemas.admin import (
    AdminOut,
    AdminTokenOut,
    OtpChallengeOut,
    OtpResendIn,
    OtpVerifyIn,
)
from app.schemas.auth import GoogleLoginIn, RefreshIn

router = APIRouter(prefix="/admin/auth", tags=["admin: staff auth"])

# One wording for "not on the staff list", "deactivated" and "that address is
# already bound to a different Google account": the answer must not help draw the
# staff list, and all three mean the same thing to the person at the door.
NOT_STAFF = "This Google account is not on the staff list"
BAD_CODE = "That code is wrong or has expired. Ask for a new one."
EXPIRED_CHALLENGE = "This sign-in attempt is no longer valid. Please sign in again."


def _issue_tokens(db: Session, admin: Admin) -> AdminTokenOut:
    raw, hashed = new_refresh_token()
    db.add(
        AdminRefreshToken(
            admin_id=admin.id,
            token_hash=hashed,
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.admin_refresh_token_days),
        )
    )
    db.commit()
    return AdminTokenOut(
        access_token=create_admin_access_token(admin.id), refresh_token=raw
    )


def _staff_for_identity(db: Session, identity) -> Admin:
    admin = db.scalar(select(Admin).where(Admin.google_sub == identity.subject))
    if admin is None:
        admin = db.scalar(select(Admin).where(Admin.email == identity.email))
    if admin is None or not admin.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, NOT_STAFF)
    if admin.google_sub not in (None, identity.subject):
        raise HTTPException(status.HTTP_403_FORBIDDEN, NOT_STAFF)
    if admin.google_sub is None:
        # The first staff sign-in binds the row to this exact Google account, so a
        # later token that claims the same address from a different subject - a
        # recreated or mistyped account - is refused rather than accepted.
        admin.google_sub = identity.subject
        db.commit()
    return admin


def _mail_or_undo(db: Session, admin: Admin, code: str) -> None:
    if send_otp(admin.email, code):
        return
    # Nothing to type means nothing to log into, so this half of the login is
    # undone rather than handed back as a challenge that can never be met.
    db.rollback()
    raise HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "The sign-in code could not be sent. Try again in a moment.",
    )


def _send_code(db: Session, admin: Admin) -> AdminOtp:
    now = datetime.now(timezone.utc)
    # One live code per person: asking again retires the old one instead of leaving
    # two codes valid at once.
    db.execute(
        update(AdminOtp)
        .where(AdminOtp.admin_id == admin.id, AdminOtp.consumed_at.is_(None))
        .values(consumed_at=now)
    )
    code, hashed = new_admin_otp()
    otp = AdminOtp(
        admin_id=admin.id,
        code_hash=hashed,
        expires_at=now + timedelta(minutes=settings.admin_otp_minutes),
    )
    db.add(otp)
    db.flush()  # the row id goes into the challenge, so it has to exist first
    _mail_or_undo(db, admin, code)
    db.commit()
    return otp


def _rearm_code(db: Session, admin: Admin, otp: AdminOtp) -> None:
    """A second code replaces the first in the same row, so the challenge the
    browser is holding keeps pointing at something live."""
    now = datetime.now(timezone.utc)
    code, hashed = new_admin_otp()
    otp.code_hash = hashed
    otp.attempts = 0
    otp.created_at = now  # the cooldown for the next resend starts here
    otp.expires_at = now + timedelta(minutes=settings.admin_otp_minutes)
    _mail_or_undo(db, admin, code)
    db.commit()


def _challenge_claims(token: str) -> tuple[int, int]:
    try:
        payload = decode_admin_token(token)
        if payload.get("type") != "admin_otp":
            raise ValueError("not a sign-in challenge")
        return int(payload["sub"]), int(payload["otp"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, EXPIRED_CHALLENGE)


@router.post(
    "/google",
    response_model=OtpChallengeOut,
    dependencies=[Depends(limit(admin_google))],
)
def staff_google_sign_in(
    data: GoogleLoginIn, request: Request, db: Session = Depends(get_db)
):
    try:
        identity = verify_id_token(data.id_token)
    except GoogleLoginDisabled:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Google sign-in is not configured on this server",
        )
    except GoogleTokenError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Google sign-in could not be verified"
        )

    consume_once(db, identity)
    admin = _staff_for_identity(db, identity)
    otp = _send_code(db, admin)
    record(db, admin, "staff.code_sent", request=request)
    db.commit()

    admin_google.reset(client_ip(request))  # Google just proved who this is
    return OtpChallengeOut(
        challenge=create_admin_otp_challenge(admin.id, otp.id),
        code_expires_in=settings.admin_otp_minutes * 60,
        resend_after=settings.admin_otp_resend_seconds,
    )


@router.post(
    "/otp/verify",
    response_model=AdminTokenOut,
    dependencies=[Depends(limit(admin_otp_verify))],
)
def staff_code_verify(
    data: OtpVerifyIn, request: Request, db: Session = Depends(get_db)
):
    admin_id, otp_id = _challenge_claims(data.challenge)
    now = datetime.now(timezone.utc)

    # Locked while it is checked, so two guesses cannot both be counted as the one
    # that finishes the attempt limit.
    otp = db.scalar(
        select(AdminOtp)
        .where(
            AdminOtp.id == otp_id,
            AdminOtp.consumed_at.is_(None),
            AdminOtp.expires_at > now,
        )
        .with_for_update()
    )
    if otp is None or otp.admin_id != admin_id:
        db.rollback()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, BAD_CODE)

    admin = db.get(Admin, admin_id)
    if admin is None or not admin.is_active:
        db.rollback()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, BAD_CODE)

    if not verify_admin_otp(data.code, otp.code_hash):
        otp.attempts += 1
        if otp.attempts >= settings.admin_otp_max_attempts:
            # Burned. A lucky guesser gets a fixed number of tries and then the
            # code has to be re-sent to whoever actually owns the mailbox.
            otp.consumed_at = now
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, BAD_CODE)

    otp.consumed_at = now
    db.commit()

    tokens = _issue_tokens(db, admin)
    record(db, admin, "staff.login", request=request)
    db.commit()
    admin_otp_verify.reset(client_ip(request))
    return tokens


@router.post(
    "/otp/resend",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(limit(admin_otp_resend))],
)
def staff_code_resend(
    data: OtpResendIn, request: Request, db: Session = Depends(get_db)
):
    admin_id, otp_id = _challenge_claims(data.challenge)
    admin = db.get(Admin, admin_id)
    if admin is None or not admin.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, NOT_STAFF)

    # The challenge names one code row. Once that row is spent the sign-in attempt
    # is over and Google has to be asked again, so a stolen challenge cannot be
    # used to keep mailing codes indefinitely.
    otp = db.get(AdminOtp, otp_id)
    if otp is None or otp.admin_id != admin_id or otp.consumed_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, EXPIRED_CHALLENGE)

    now = datetime.now(timezone.utc)
    waited = (now - otp.created_at).total_seconds()
    if waited < settings.admin_otp_resend_seconds:
        wait = int(settings.admin_otp_resend_seconds - waited) + 1
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"The code is still on its way. Ask again in {wait} seconds.",
            headers={"Retry-After": str(wait)},
        )

    _rearm_code(db, admin, otp)
    record(db, admin, "staff.code_sent", request=request)
    db.commit()
    return {"status": "sent"}


@router.post(
    "/refresh",
    response_model=AdminTokenOut,
    dependencies=[Depends(limit(admin_refresh_window))],
)
def staff_refresh(data: RefreshIn, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    # One atomic statement: only one request can ever retire this token.
    row = db.execute(
        update(AdminRefreshToken)
        .where(
            AdminRefreshToken.token_hash == hash_token(data.refresh_token),
            AdminRefreshToken.revoked_at.is_(None),
            AdminRefreshToken.expires_at > now,
        )
        .values(revoked_at=now)
        .returning(AdminRefreshToken.admin_id)
    ).first()

    if not row:
        db.rollback()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")

    admin = db.get(Admin, row.admin_id)
    if admin is None or not admin.is_active:
        db.rollback()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Staff account disabled")

    return _issue_tokens(db, admin)


@router.post("/logout", status_code=204)
def staff_logout(data: RefreshIn, db: Session = Depends(get_db)):
    db.execute(
        update(AdminRefreshToken)
        .where(
            AdminRefreshToken.token_hash == hash_token(data.refresh_token),
            AdminRefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(timezone.utc))
    )
    db.commit()


@router.get("/me", response_model=AdminOut)
def staff_me(admin: Admin = Depends(get_current_admin)):
    return admin
