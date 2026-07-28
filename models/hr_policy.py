"""Company-scoped, versioned HR policy model.

Uploaded policies are immediately available to employees unless an
administrator moves the version to the Bin. Bin records may be restored or
permanently removed through the protected administrator workflow.
"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin


class HRPolicy(TimestampMixin, Base):
    """One version of a company policy file."""

    __tablename__ = "hr_policies"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "title", "version",
            name="uq_hr_policies_company_title_version",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str | None] = mapped_column(
        String(30), unique=True, index=True, nullable=True,
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False,
    )
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(30), default="1.0", nullable=False)

    # Uploaded files use published/trashed. Legacy draft/archived values are
    # retained for backward-compatible databases and manual API tests.
    status: Mapped[str] = mapped_column(
        String(20), index=True, default="published", nullable=False,
    )
    effective_date: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    trashed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    trashed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=True,
    )
