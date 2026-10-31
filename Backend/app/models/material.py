import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class MaterialStatus(str, enum.Enum):
    pending = "pending"        # uploaded, waiting for the worker
    processing = "processing"  # worker is converting it
    ready = "ready"            # pages are available to students
    failed = "failed"          # see the error column


class Material(Base):
    __tablename__ = "materials"
    __table_args__ = (
        # The worker walks unfinished jobs in id order and stops at the first one.
        # A partial index on the id alone gives it that order and stays tiny while
        # the ready archive grows around it; a full index would sort rows it never reads.
        Index(
            "ix_materials_claimable",
            "id",
            postgresql_where=text("status IN ('pending', 'processing')"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # RESTRICT: a topic that still has materials cannot be deleted (files would be orphaned)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topics.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    original_key: Mapped[str] = mapped_column(String(255), unique=True)
    size_bytes: Mapped[int]
    page_count: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[MaterialStatus] = mapped_column(
        Enum(MaterialStatus), default=MaterialStatus.pending, index=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(default=0)
    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Set after a failed attempt so a broken PDF is retried with backoff instead
    # of being re-claimed on every three second poll.
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
