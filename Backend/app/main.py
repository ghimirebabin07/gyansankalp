from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.storage import get_storage
from app.routers import (
    admin_courses, admin_enrollments, admin_materials, auth, courses, materials,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.s3_create_bucket:  # development only
        get_storage().ensure_bucket()
    yield


app = FastAPI(title="GyanSankalp API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(auth.router)
app.include_router(courses.router)
app.include_router(materials.router)
app.include_router(admin_courses.router)
app.include_router(admin_enrollments.router)
app.include_router(admin_materials.router)


@app.get("/health")
def health():
    return {"status": "ok"}
