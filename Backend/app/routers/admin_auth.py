from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_admin
from app.core.login_guard import is_locked, register_failure, register_success
from app.core.ratelimit import admin_login, client_ip, limit
from app.core.security import (
    hash_password,
    verify_password,
    create_admin_access_token,
)
from app.db.session import get_db
from app.models.admin import Admin
from app.schemas.admin import AdminLoginIn, AdminOut, AdminTokenOut

router = APIRouter(prefix="/admin/auth", tags=["admin auth"])

# Same cost for an unknown email as for a wrong password.
DUMMY_HASH = hash_password("not-a-real-password")


@router.post("/login", response_model=AdminTokenOut, dependencies=[Depends(limit(admin_login))])
def admin_login(
    request: Request, data: AdminLoginIn, db: Session = Depends(get_db)
):
    now = datetime.now(timezone.utc)
    admin = db.scalar(select(Admin).where(Admin.email == data.email.lower()))
    if admin is None:
        verify_password(data.password, DUMMY_HASH)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    if not admin.is_active or is_locked(admin, now):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    if not verify_password(data.password, admin.password_hash):
        register_failure(db, admin, now)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    register_success(db, admin)
    admin_login.reset(client_ip(request))
    return AdminTokenOut(
        access_token=create_admin_access_token(admin.id),
    )


@router.get("/me", response_model=AdminOut)
def admin_me(admin: Admin = Depends(get_current_admin)):
    return admin
