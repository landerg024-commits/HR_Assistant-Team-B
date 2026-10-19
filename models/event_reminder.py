"""Company-scoped planning reminder for future events and activities."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin


class EventReminder(TimestampMixin, Base):
    """One smart planning item that may exist before any announcement."""

    __tablename__ = "event_reminders"
    __table_args__ = (
        UniqueConstraint(
            "public_id",
            name="uq_event_reminders_public_id",
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

    title: Mapped[str] = mapped_column(String(180), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    event_start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=False,
    )
    event_end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    # Legacy single-reminder columns are retained for safe compatibility with
    # databases created by v8.8.23-v8.8.24. New logic uses the three fixed
    # milestone fields below.
    reminder_lead_minutes: Mapped[int] = mapped_column(
        Integer,
        default=43200,
        server_default="43200",
        nullable=False,
    )
    reminder_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=False,
    )
    reminder_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    reminder_one_month_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    reminder_two_weeks_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    reminder_one_week_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    status: Mapped[str] = mapped_column(
        String(24),
        default="planned",
        server_default="planned",
        nullable=False,
        index=True,
    )
    announcement_id: Mapped[int | None] = mapped_column(
        ForeignKey("announcements.id", ondelete="SET NULL"),
        index=True,
    )

    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    archived_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
