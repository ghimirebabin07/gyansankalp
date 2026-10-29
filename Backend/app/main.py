from fastapi import FastAPI

from app.routers import auth, admin_courses, admin_enrollments, courses

app = FastAPI(title="GyanSankalp API")
app.include_router(auth.router)
app.include_router(courses.router)
app.include_router(admin_courses.router)
app.include_router(admin_enrollments.router)


@app.get("/health")
def health():
    return {"status": "ok"}
