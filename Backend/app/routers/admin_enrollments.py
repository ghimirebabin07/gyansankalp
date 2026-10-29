from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import admin_only
from app.db.session import get_db
from app.models.course import Course
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.models.user import User
from app.schemas.enrollment import EnrollmentGrant, EnrollmentOut

router = APIRouter(
    prefix="/admin/enrollments",
    tags=["admin: enrollments"],
    dependencies=[Depends(admin_only)],
)


@router.post("", response_model=EnrollmentOut, status_code=201)
def grant_access(body: EnrollmentGrant, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if not user:
        raise HTTPException(404, "No user with that email")
    if not db.get(Course, body.course_id):
        raise HTTPException(404, "Course not found")

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=body.days) if body.days else None

    enrollment = db.scalar(
        select(Enrollment).where(
            Enrollment.user_id == user.id, Enrollment.course_id == body.course_id
        )
    )
    if enrollment:  # re-granting renews an old or revoked enrollment
        enrollment.status = EnrollmentStatus.active
        enrollment.starts_at = now
        enrollment.expires_at = expires_at
    else:
        enrollment = Enrollment(
            user_id=user.id, course_id=body.course_id,
            starts_at=now, expires_at=expires_at,
        )
        db.add(enrollment)
    try:
        db.commit()
    except IntegrityError:  # two admins granting at the same moment
        db.rollback()
        raise HTTPException(409, "Enrollment already exists, try again")
    db.refresh(enrollment)
    return enrollment


@router.get("", response_model=list[EnrollmentOut])
def list_enrollments(
    course_id: int | None = None,
    user_id: int | None = None,
    status: EnrollmentStatus | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(Enrollment).order_by(Enrollment.id.desc()).limit(limit).offset(offset)
    if course_id is not None:
        stmt = stmt.where(Enrollment.course_id == course_id)
    if user_id is not None:
        stmt = stmt.where(Enrollment.user_id == user_id)
    if status is not None:
        stmt = stmt.where(Enrollment.status == status)
    return db.scalars(stmt).all()


@router.post("/{enrollment_id}/revoke", response_model=EnrollmentOut)
def revoke(enrollment_id: int, db: Session = Depends(get_db)):
    # one atomic UPDATE, safe to call twice
    db.execute(
        update(Enrollment)
        .where(Enrollment.id == enrollment_id, Enrollment.status != EnrollmentStatus.revoked)
        .values(status=EnrollmentStatus.revoked)
    )
    db.commit()
    enrollment = db.get(Enrollment, enrollment_id)
    if not enrollment:
        raise HTTPException(404, "Enrollment not found")
    db.refresh(enrollment)
    return enrollment
