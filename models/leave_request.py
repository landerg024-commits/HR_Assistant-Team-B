"""Employee leave request sent to an assigned department manager."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin
from models.employee import Employee
from models.leave_type import LeaveType


class LeaveRequest(TimestampMixin, Base):
    """One leave request monitored by HR without an admin approval action."""

    __tablename__ = "leave_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    public_id: Mapped[str | None] = mapped_column(
        String(30), unique=True, index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    leave_type_id: Mapped[int] = mapped_column(
        ForeignKey("leave_types.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    manager_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"),
        index=True,
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    requested_days: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="sent_to_manager", nullable=False, index=True
    )
    manager_email: Mapped[str] = mapped_column(String(255), nullable=False)
    cc_emails_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    email_status: Mapped[str] = mapped_column(
        String(30), default="pending", nullable=False
    )
    email_reference: Mapped[str | None] = mapped_column(String(500))
    email_error: Mapped[str | None] = mapped_column(String(500))
    attachment_original_filename: Mapped[str | None] = mapped_column(String(255))
    attachment_storage_path: Mapped[str | None] = mapped_column(String(700))
    attachment_mime_type: Mapped[str | None] = mapped_column(String(150))
    attachment_size_bytes: Mapped[int | None] = mapped_column()
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    employee: Mapped[Employee] = relationship(
        foreign_keys=[employee_id], lazy="joined"
    )
    manager: Mapped[Employee | None] = relationship(
        foreign_keys=[manager_employee_id], lazy="joined"
    )
    leave_type: Mapped[LeaveType] = relationship(lazy="joined")
