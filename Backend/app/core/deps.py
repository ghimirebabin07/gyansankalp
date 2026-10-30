import jwt  # type: ignore
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.admin import Admin
from app.models.user import User, Role

oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")
admin_oauth2 = OAuth2PasswordBearer(tokenUrl="/admin/auth/login")


def get_current_user(
    token: str = Depends(oauth2), db: Session = Depends(get_db)
) -> User:
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or disabled")
    return user


def admin_only(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user


def get_current_admin(
    token: str = Depends(admin_oauth2), db: Session = Depends(get_db)
) -> Admin:
    try:
        payload = decode_access_token(token)
        if payload.get("type") != "admin":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
        admin_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    admin = db.get(Admin, admin_id)
    if not admin or not admin.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Admin not found or disabled")
    return admin 