import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.google import (
    GoogleIdentity,
    GoogleLoginDisabled,
    GoogleTokenError,
    consume_once,
    verify_id_token,
)
from app.core.login_guard import (
    credentials_are_plausible,
    is_locked,
    register_failure,
    register_success,
)
from app.core.mail import send_verification
from app.core.ratelimit import (
    auth_google,
    auth_login,
    auth_refresh,
    auth_register,
    auth_resend_verification,
    auth_verify,
    client_ip,
    limit,
)
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    hash_token,
    new_refresh_token,
    hash_refresh_token,
    new_verification_token,
)
from app.db.session import get_db
from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.schemas.auth import (
    GoogleLoginIn,
    GoogleTokenOut,
    RefreshIn,
    RegisterIn,
    ResendVerificationIn,
    TokenOut,
    UserOut,
    VerifyEmailIn,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# Verified when no account matches, so a missing user costs the same as a wrong
# password and response time stays a bad way to probe for accounts.
DUMMY_HASH = hash_password("not-a-real-password")


def _bad_credentials() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")


def issue_tokens(db: Session, user: User) -> TokenOut:
    raw, hashed = new_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hashed,
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.refresh_token_days),
        )
    )
    db.commit()
    return TokenOut(
        access_token=create_access_token(user.id, user.role.value),
        refresh_token=raw,
    )


def _send_verification_link(db: Session, user: User) -> None:
    """Store only the hash, so a database leak cannot produce live links."""
    raw, hashed = new_verification_token()
    user.email_verify_hash = hashed
    user.email_verify_expires_at = (
        datetime.now(timezone.utc) + timedelta(hours=settings.email_verify_hours)
    )
    db.commit()
    send_verification(user.email, f"{settings.verify_link_base}?token={raw}")


@router.post(
    "/register",
    response_model=UserOut,
    status_code=201,
    dependencies=[Depends(limit(auth_register))],
)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    # Answered from the email alone so the wording can point a returning student at
    # the login door; the unique index still decides anything that races past this.
    if db.scalar(select(User.id).where(User.email == data.email.lower())) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This email is already registered. Please login."
        )
    user = User(
        full_name=data.full_name.strip(),
        email=data.email.lower(),
        phone=data.phone,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Email or phone already registered"
        )
    db.refresh(user)
    _send_verification_link(db, user)
    return user


@router.post("/login", response_model=TokenOut, dependencies=[Depends(limit(auth_login))])
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    if not credentials_are_plausible(form.username, form.password):
        raise _bad_credentials()

    # Swagger sends the email in the "username" field
    user = db.scalar(select(User).where(User.email == form.username.lower()))
    if user is None:
        verify_password(form.password, DUMMY_HASH)
        raise _bad_credentials()

    if not user.is_active or is_locked(user, now):
        raise _bad_credentials()

    if not verify_password(form.password, user.password_hash):
        register_failure(db, user, now)
        raise _bad_credentials()

    register_success(db, user)
    auth_login.reset(client_ip(request))  # a proven human is not a brute-forcer
    return issue_tokens(db, user)


@router.post("/refresh", response_model=TokenOut, dependencies=[Depends(limit(auth_refresh))])
def refresh(data: RefreshIn, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    # One atomic statement: only one request can ever revoke this token.
    row = db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == hash_refresh_token(data.refresh_token),
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        )
        .values(revoked_at=now)
        .returning(RefreshToken.user_id)
    ).first()

    if not row:
        db.rollback()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")

    user = db.get(User, row.user_id)
    if not user or not user.is_active:
        db.rollback()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User disabled")

    return issue_tokens(db, user)  # commits the revoke and the new token together


@router.post("/logout", status_code=204)
def logout(data: RefreshIn, db: Session = Depends(get_db)):
    db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == hash_refresh_token(data.refresh_token),
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(timezone.utc))
    )
    db.commit()


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


def _account_for_identity(
    db: Session, identity: GoogleIdentity, password: str | None = None
) -> tuple[User, bool]:
    """The student behind a verified Google identity, and whether we just made them."""
    now = datetime.now(timezone.utc)

    user = db.scalar(select(User).where(User.google_sub == identity.subject))
    if user is not None:
        return user, False

    user = db.scalar(select(User).where(User.email == identity.email))
    if user is None:
        # Without a password from the register page this gets an unusable hash: there
        # is no password, and the login route must not become a way to walk into a
        # Google-only account.
        user = User(
            full_name=identity.full_name,
            email=identity.email,
            phone=None,
            google_sub=identity.subject,
            email_verified_at=now,
            password_hash=hash_password(password or secrets.token_urlsafe(32)),
        )
        db.add(user)
        try:
            db.commit()
            db.refresh(user)
            return user, True
        except IntegrityError:
            # Someone created that address while this request was running.
            db.rollback()
            user = db.scalar(select(User).where(User.email == identity.email))
            if user is None:
                raise HTTPException(
                    status.HTTP_401_UNAUTHORIZED, "Google sign-in could not be completed"
                )

    if user.google_sub not in (None, identity.subject):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This account is already linked to a different Google account",
        )
    # Google only signs a token for an address it has proved it can read, so this
    # sign-in carries the same proof the confirmation link was meant to bring. A
    # student who registered by password and lost that link is not shut out of
    # their own address by whoever typed it first.
    user.google_sub = identity.subject
    if not user.email_verified_at:
        user.email_verified_at = now
    db.commit()
    return user, False


@router.post("/google", response_model=GoogleTokenOut, dependencies=[Depends(limit(auth_google))])
def google_sign_in(data: GoogleLoginIn, request: Request, db: Session = Depends(get_db)):
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
    user, created = _account_for_identity(db, identity, data.password)
    if not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account disabled")

    auth_google.reset(client_ip(request))  # Google already proved who this is
    return GoogleTokenOut(**issue_tokens(db, user).model_dump(), created=created)


@router.post(
    "/verify-email",
    response_model=UserOut,
    dependencies=[Depends(limit(auth_verify))],
)
def verify_email(data: VerifyEmailIn, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    # Atomic, like refresh: one click wins, every retry after it reads as invalid.
    row = db.execute(
        update(User)
        .where(
            User.email_verify_hash == hash_token(data.token),
            User.email_verify_expires_at > now,
        )
        .values(email_verified_at=now, email_verify_hash=None, email_verify_expires_at=None)
        .returning(User.id)
    ).first()
    if not row:
        db.rollback()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "That confirmation link is invalid or has expired"
        )
    db.commit()
    return db.get(User, row.id)


@router.post(
    "/resend-verification",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(limit(auth_resend_verification))],
)
def resend_verification(data: ResendVerificationIn, db: Session = Depends(get_db)) -> dict:
    """Answers identically whether or not the address is registered."""
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if user is not None and user.is_active and not user.email_verified_at:
        _send_verification_link(db, user)
    return {"status": "sent"}