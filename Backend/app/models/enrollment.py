import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class EnrollmentStatus(str, enum.Enum):
    active = "active"
    expired = "expired"
    revoked = "revoked"


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("user_id", "course_id", name="uq_enrollment_user_course"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # RESTRICT: a course with enrollments cannot be deleted (keeps payment history)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[EnrollmentStatus] = mapped_column(
        Enum(EnrollmentStatus), default=EnrollmentStatus.active
    )
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )  # NULL = lifetime access
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
