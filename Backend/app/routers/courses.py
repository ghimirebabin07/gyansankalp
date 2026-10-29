from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.access import active_conditions
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.user import User
from app.schemas.course import CourseDetail, CourseOut

router = APIRouter(tags=["courses"])


@router.get("/courses", response_model=list[CourseOut])
def list_courses(db: Session = Depends(get_db)):
    stmt = select(Course).where(Course.is_published.is_(True)).order_by(Course.id)
    return db.scalars(stmt).all()


@router.get("/courses/{slug}", response_model=CourseDetail)
def get_course(slug: str, db: Session = Depends(get_db)):
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
