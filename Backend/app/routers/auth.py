from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.login_guard import is_locked, register_failure, register_success
from app.core.ratelimit import auth_login, auth_refresh, auth_register, client_ip, limit
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    new_refresh_token,
    hash_refresh_token,
)
from app.db.session import get_db
from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.schemas.auth import RegisterIn, UserOut, TokenOut, RefreshIn

router = APIRouter(prefix="/auth", tags=["auth"])

# Verified when no account matches, so a missing user costs the same as a wrong
# password and response time stays a bad way to probe for accounts.
DUMMY_HASH = hash_password("not-a-real-password")


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


@router.post(
    "/register",
    response_model=UserOut,
    status_code=201,
    dependencies=[Depends(limit(auth_register))],
)
def register(data: RegisterIn, db: Session = Depends(get_db)):
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
    return user


@router.post("/login", response_model=TokenOut, dependencies=[Depends(limit(auth_login))])
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    # Swagger sends the email in the "username" field
    user = db.scalar(select(User).where(User.email == form.username.lower()))
    if user is None:
        verify_password(form.password, DUMMY_HASH)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")

    if not user.is_active or is_locked(user, now):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")

    if not verify_password(form.password, user.password_hash):
        register_failure(db, user, now)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")

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