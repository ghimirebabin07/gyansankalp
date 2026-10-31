from contextlib import asynccontextmanager
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.core.config import settings
from app.core.headers import SecurityMiddleware
from app.core.security import hash_password
from app.core.storage import get_storage
from app.db.session import SessionLocal
from app.models.admin import Admin
from app.routers import (
    admin_auth, admin_courses, admin_enrollments, admin_materials, auth, courses, enrollments, materials,
)


def setup_initial_admin():
    """Create initial admin from env vars if needed. Enforces security by crashing if env vars exist after admin is created."""
    has_env_vars = all([
        settings.initial_admin_email,
        settings.initial_admin_password,
        settings.initial_admin_name,
    ])

    if not has_env_vars:
        return

    db = SessionLocal()
    try:
        admin_count = db.scalar(select(Admin.id))
        if admin_count is not None:
            print("\n" + "=" * 70, file=sys.stderr)
            print("SECURITY ERROR: Initial admin credentials still in environment!", file=sys.stderr)
            print("Admin account already exists. Remove these env vars immediately:", file=sys.stderr)
            print("  - INITIAL_ADMIN_EMAIL", file=sys.stderr)
            print("  - INITIAL_ADMIN_PASSWORD", file=sys.stderr)
            print("  - INITIAL_ADMIN_NAME", file=sys.stderr)
            print("Then restart the application.", file=sys.stderr)
            print("=" * 70 + "\n", file=sys.stderr)
            sys.exit(1)

        if len(settings.initial_admin_password) < 12:
            raise RuntimeError(
                "INITIAL_ADMIN_PASSWORD must be at least 12 characters; the admin "
                "account is the whole backend"
            )

        admin = Admin(
            email=settings.initial_admin_email.lower(),
            full_name=settings.initial_admin_name,
            password_hash=hash_password(settings.initial_admin_password),
            is_active=True,
        )
        db.add(admin)
        db.commit()
        print("\n" + "=" * 70)
        print(f"Initial admin created: {admin.email}")
        print("IMPORTANT: Remove INITIAL_ADMIN_* env vars and restart!")
        print("=" * 70 + "\n")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_initial_admin()
    if settings.s3_create_bucket:  # development only
        get_storage().ensure_bucket()
    yield


app = FastAPI(
    title="GyanSankalp API",
    lifespan=lifespan,
    docs_url="/docs" if settings.expose_docs else None,
    redoc_url="/redoc" if settings.expose_docs else None,
    openapi_url="/openapi.json" if settings.expose_docs else None,
)
# SecurityMiddleware goes first so CORS ends up outermost and answers preflight.
app.add_middleware(SecurityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(auth.router)
app.include_router(courses.router)
app.include_router(enrollments.router)
app.include_router(materials.router)
app.include_router(admin_auth.router)
app.include_router(admin_courses.router)
app.include_router(admin_enrollments.router)
app.include_router(admin_materials.router)


@app.get("/health")
def health():
    return {"status": "ok"}
