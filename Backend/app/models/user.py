import enum
from datetime import datetime

from sqlalchemy import Integer, String, DateTime, Enum, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Role(str, enum.Enum):
    student = "student"
    admin = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # Google accounts have no Nepali mobile number, and a unique column full of
    # the same placeholder would collide on the second one. Postgres allows any
    # number of NULLs in a unique index, so optional stays safe.
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True, unique=True)
    # Google's stable subject id. Nullable because password accounts have none.
    google_sub: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)
    # Password accounts prove nothing about the address until they click the link,
    # and only a proven address may be matched to a Google identity.
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    email_verify_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email_verify_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.student)
    is_active: Mapped[bool] = mapped_column(default=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None


class GoogleTokenUse(Base):
    """One row per Google ID token already exchanged for our own tokens.

    A Google ID token stays valid for about an hour, so without this a token
    lifted from a browser could be replayed against /auth/google at will.
    """

    __tablename__ = "google_token_uses"

    sub: Mapped[str] = mapped_column(String(32), primary_key=True)
    issued_at: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
