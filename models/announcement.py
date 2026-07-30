"""Company-scoped announcement and activity post model."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin


class Announcement(TimestampMixin, Base):
    """One draft, scheduled, published, or archived company announcement."""

    __tablename__ = "announcements"
    __table_args__ = (
        UniqueConstraint(
            "public_id",
            name="uq_announcements_public_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str | None] = mapped_column(
        String(30),
        unique=True,
        index=True,
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    updated_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(180),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    summary: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="draft",
        server_default="draft",
        nullable=False,
        index=True,
    )
    is_pinned: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="0",
        nullable=False,
        index=True,
    )

    publish_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    notification_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    image_original_filename: Mapped[str | None] = mapped_column(
        String(255)
    )
    image_storage_path: Mapped[str | None] = mapped_column(
        String(500)
    )
    image_mime_type: Mapped[str | None] = mapped_column(
        String(120)
    )
    image_size_bytes: Mapped[int | None] = mapped_column(
        Integer
    )
