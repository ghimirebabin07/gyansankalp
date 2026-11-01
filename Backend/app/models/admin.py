import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class AdminRole(str, enum.Enum):
    super_admin = "super_admin"
    content_manager = "content_manager"
    editor = "editor"


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    # Staff sign in with Google plus a code, so nobody authenticates with this
    # column any more. It stays until the old rows are retired for good; seeded
    # accounts carry a hash of a random string nobody knows.
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[AdminRole] = mapped_column(
        Enum(AdminRole, name="admin_role"),
        default=AdminRole.super_admin,
        server_default="super_admin",
    )
    # Google's stable subject id, bound on first sign-in. Two accounts can share a
    # display name but never the same subject, so this is what says the person
    # standing at the login page is the staff member the row was made for.
    google_sub: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    # Kept for the shared lockout helpers; only student login uses them now.
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    @property
    def google_linked(self) -> bool:
        return self.google_sub is not None


class AdminOtp(Base):
    """One sign-in code. Stored as a hash, spent once, dead after five minutes."""

    __tablename__ = "admin_otps"
    __table_args__ = (Index("ix_admin_otps_admin_open", "admin_id", "consumed_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_id: Mapped[int] = mapped_column(
        ForeignKey("admins.id", ondelete="CASCADE"), index=True
    )
    # An argon2 hash rather than a digest: a six digit code is only a million
    # possibilities, so a fast hash would let a database leak be unwound offline
    # inside the code's own five minutes.
    code_hash: Mapped[str] = mapped_column(String(255), unique=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AdminRefreshToken(Base):
    """Keeps an admin signed in for a working day without a code every 15 minutes.

    These rows are the revocation list: deleting one ends that session at its next
    refresh, which is what a deactivated staff account needs to hit.
    """

    __tablename__ = "admin_refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_id: Mapped[int] = mapped_column(
        ForeignKey("admins.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CourseAssignment(Base):
    """Which courses an editor may touch. Other roles are unscoped."""

    __tablename__ = "course_assignments"

    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True
    )
    admin_id: Mapped[int] = mapped_column(
        ForeignKey("admins.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AdminActivityLog(Base):
    """Who did what in the admin panel. Kept after the staff row is gone."""

    __tablename__ = "admin_activity_logs"
    __table_args__ = (
        Index("ix_admin_activity_logs_admin_created", "admin_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admins.id", ondelete="SET NULL"), index=True, nullable=True
    )
    action: Mapped[str] = mapped_column(String(60))
    target: Mapped[str | None] = mapped_column(String(160), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
