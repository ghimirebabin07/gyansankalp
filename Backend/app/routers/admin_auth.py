from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_admin
from app.core.security import (
    verify_password,
    create_admin_access_token,
)
from app.db.session import get_db
from app.models.admin import Admin
from app.schemas.admin import AdminLoginIn, AdminOut, AdminTokenOut

router = APIRouter(prefix="/admin/auth", tags=["admin auth"])


@router.post("/login", response_model=AdminTokenOut)
def admin_login(data: AdminLoginIn, db: Session = Depends(get_db)):
    admin = db.scalar(select(Admin).where(Admin.email == data.email.lower()))
    if not admin or not admin.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not verify_password(data.password, admin.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return AdminTokenOut(
        access_token=create_admin_access_token(admin.id),
    )


@router.get("/me", response_model=AdminOut)
def admin_me(admin: Admin = Depends(get_current_admin)):
    return admin
