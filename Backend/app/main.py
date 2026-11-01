from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.errors import install_error_handlers
from app.core.headers import SecurityMiddleware
from app.core.observability import RequestMiddleware, configure_logging
from app.core.storage import get_storage
from app.db.session import SessionLocal
from app.routers import (
    admin_auth, admin_courses, admin_enrollments, admin_materials, admin_staff, auth, courses, enrollments, materials,
)

configure_logging()
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # uvicorn installs its own logging config after this module is imported, so
    # the shape is re-applied here: without it the boot lines a log shipper reads
    # are half plain text, half JSON.
    configure_logging()
    if settings.s3_create_bucket:  # development only
        get_storage().ensure_bucket()
    log.info(
        "api ready",
        extra={"env": settings.app_env, "workers_note": "rate limits are per process"},
    )
    yield
    log.info("api stopped")


app = FastAPI(
    title="GyanSankalp API",
    lifespan=lifespan,
    docs_url="/docs" if settings.expose_docs else None,
    redoc_url="/redoc" if settings.expose_docs else None,
    openapi_url="/openapi.json" if settings.expose_docs else None,
)
install_error_handlers(app)
# Added last so it runs outermost: every request, preflights included, gets an id.
app.add_middleware(SecurityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Request-Id", "Retry-After"],
)
app.add_middleware(RequestMiddleware)
app.include_router(auth.router)
app.include_router(courses.router)
app.include_router(enrollments.router)
app.include_router(materials.router)
app.include_router(admin_auth.router)
app.include_router(admin_courses.router)
app.include_router(admin_enrollments.router)
app.include_router(admin_materials.router)
app.include_router(admin_staff.router)


@app.get("/health")
def health():
    """Liveness only: no database, no storage, so a slow dependency cannot restart us."""
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness for an orchestrator or the load balancer.

    Reports which dependency is unreachable but never why, because the reason
    contains hostnames and credentials the public has no business seeing.
    """
    checks = {"database": False, "storage": False}
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        log.error("readiness: database unreachable")

    try:
        get_storage().ping()
        checks["storage"] = True
    except Exception:
        log.error("readiness: object storage unreachable")

    healthy = all(checks.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ready" if healthy else "degraded", **checks},
    )
