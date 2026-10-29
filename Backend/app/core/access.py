from sqlalchemy import or_, func, select
from sqlalchemy.orm import Session

from app.models.enrollment import Enrollment, EnrollmentStatus


def active_conditions():
    """SQL conditions meaning 'this enrollment gives access right now'.

    Checks expires_at directly, so access stops on time even if the
    scheduler has not flipped the status to 'expired' yet.
    """
    return [
        Enrollment.status == EnrollmentStatus.active,
        or_(Enrollment.expires_at.is_(None), Enrollment.expires_at > func.now()),
    ]


def has_course_access(db: Session, user_id: int, course_id: int) -> bool:
    stmt = (
        select(Enrollment.id)
        .where(
            Enrollment.user_id == user_id,
            Enrollment.course_id == course_id,
            *active_conditions(),
        )
        .limit(1)
    )
    return db.scalar(stmt) is not None
