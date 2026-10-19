"""Company-scoped leave type and rule configuration."""

from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin


class LeaveType(TimestampMixin, Base):
    """One configurable leave category owned by a company."""

    __tablename__ = "leave_types"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "code",
            name="uq_leave_types_company_code",
        ),
        UniqueConstraint(
            "company_id",
            "name",
            name="uq_leave_types_company_name",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    annual_credits: Mapped[Decimal] = mapped_column(
        Numeric(8, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    is_paid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    carry_over_limit: Mapped[Decimal] = mapped_column(
        Numeric(8, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    # Legacy field remains for database compatibility. New leave
    # requests use ``handover_plan_requirement`` instead.
    requires_attachment: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    handover_plan_requirement: Mapped[str] = mapped_column(
        String(20),
        default="optional",
        server_default="optional",
        nullable=False,
    )
    minimum_notice_days: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
