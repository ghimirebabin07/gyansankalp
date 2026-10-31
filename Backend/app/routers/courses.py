from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.access import active_conditions
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.course import Course, Topic
from app.models.enrollment import Enrollment
from app.models.material import Material
from app.models.user import User
from app.schemas.course import CourseDetail, CourseOut

router = APIRouter(tags=["courses"])

LIKE_ESCAPE = "\\"


def _like_contains(value: str) -> str:
    """A user-supplied % or _ is data, not a wildcard."""
    escaped = (
        value.replace(LIKE_ESCAPE, LIKE_ESCAPE + LIKE_ESCAPE)
        .replace("%", LIKE_ESCAPE + "%")
        .replace("_", LIKE_ESCAPE + "_")
    )
    return f"%{escaped}%"


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """Public stats for the homepage counters."""
    course_count = db.scalar(select(func.count(Course.id)).where(Course.is_published.is_(True))) or 0
    topic_count = db.scalar(
        select(func.count(Topic.id))
        .join(Course, Topic.course_id == Course.id)
        .where(Course.is_published.is_(True))
    ) or 0
    material_count = db.scalar(
        select(func.count(Material.id))
        .join(Topic, Material.topic_id == Topic.id)
        .join(Course, Topic.course_id == Course.id)
        .where(Course.is_published.is_(True), Material.status == "ready")
    ) or 0
    return {"courses": course_count, "topics": topic_count, "materials": material_count}


@router.get("/courses", response_model=list[CourseOut])
def list_courses(
    level: str | None = Query(
        None,
        min_length=1,
        max_length=50,
        description="Filter by exam level (e.g. kharidar, nasu, officer)",
    ),
    db: Session = Depends(get_db),
):
    stmt = select(Course).where(Course.is_published.is_(True)).order_by(Course.id)
    if level:
        stmt = stmt.where(
            Course.exam_level.ilike(_like_contains(level), escape=LIKE_ESCAPE)
        )
    return db.scalars(stmt).all()


@router.get("/courses/{slug}", response_model=CourseDetail)
def get_course(slug: str = Path(min_length=1, max_length=120), db: Session = Depends(get_db)):
    stmt = (
        select(Course)
        .options(selectinload(Course.topics))
        .where(Course.slug == slug, Course.is_published.is_(True))
    )
    course = db.scalar(stmt)
    if not course:
        raise HTTPException(404, "Course not found")
    return course


@router.get("/me/courses", response_model=list[CourseOut])
def my_courses(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = (
        select(Course)
        .join(Enrollment, Enrollment.course_id == Course.id)
        .where(Enrollment.user_id == user.id, *active_conditions())
        .order_by(Course.id)
    )
    return db.scalars(stmt).all()
