"""Per-employee annual leave credit balances."""

from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin
from models.employee import Employee
from models.leave_type import LeaveType


class LeaveBalance(TimestampMixin, Base):
    """One employee's balance for one leave type and calendar year."""

    __tablename__ = "leave_balances"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "employee_id",
            "leave_type_id",
            "year",
            name="uq_leave_balances_employee_type_year",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    leave_type_id: Mapped[int] = mapped_column(
        ForeignKey("leave_types.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    year: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    allocated_days: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), default=Decimal("0.00"), nullable=False
    )
    carry_over_days: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), default=Decimal("0.00"), nullable=False
    )
    adjustment_days: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), default=Decimal("0.00"), nullable=False
    )
    used_days: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), default=Decimal("0.00"), nullable=False
    )
    reserved_days: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), default=Decimal("0.00"), nullable=False
    )

    employee: Mapped[Employee] = relationship(lazy="joined")
    leave_type: Mapped[LeaveType] = relationship(lazy="joined")

    @hybrid_property
    def remaining_days(self) -> Decimal:
        """Return currently available credits after reservations."""

        return (
            Decimal(self.allocated_days)
            + Decimal(self.carry_over_days)
            + Decimal(self.adjustment_days)
            - Decimal(self.used_days)
            - Decimal(self.reserved_days)
        )
