from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.ratelimit import enrollment_request, limit
from app.db.session import get_db
from app.models.course import Course
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.models.user import User
from app.schemas.enrollment import EnrollmentOut

router = APIRouter(prefix="/enrollments", tags=["enrollments"])


@router.post(
    "",
    response_model=EnrollmentOut,
    status_code=201,
    dependencies=[Depends(limit(enrollment_request))],
)
def request_enrollment(
    course_id: int = Query(gt=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Students request enrollment. Admin must approve before access is granted."""
    course = db.get(Course, course_id)
    if not course or not course.is_published:
        raise HTTPException(404, "Course not found")

    # Check if already enrolled
    existing = db.scalar(
        select(Enrollment).where(
            Enrollment.user_id == user.id,
            Enrollment.course_id == course_id,
        )
    )
    if existing:
        if existing.status == EnrollmentStatus.active:
            raise HTTPException(409, "Already enrolled in this course")
        if existing.status == EnrollmentStatus.pending:
            raise HTTPException(409, "Enrollment request pending admin approval")
        # Reactivate revoked/expired enrollment
        existing.status = EnrollmentStatus.active if course.price_npr == 0 else EnrollmentStatus.pending
        existing.starts_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        return existing

    enrollment = Enrollment(
        user_id=user.id,
        course_id=course_id,
        status=EnrollmentStatus.active if course.price_npr == 0 else EnrollmentStatus.pending,
        starts_at=datetime.now(timezone.utc),
        expires_at=None,
    )
    db.add(enrollment)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Enrollment request already exists")
    db.refresh(enrollment)
    return enrollment
