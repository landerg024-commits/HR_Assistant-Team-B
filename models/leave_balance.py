"""Per-employee annual leave credit balances."""

from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, UniqueConstraint, text
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

    # Phase 1 leave-ledger columns. The legacy allocation/carry-over fields
    # remain in place so older databases, services, and audit history are
    # preserved while the new table uses clearer accounting labels.
    beginning_credit_days: Mapped[Decimal] = mapped_column(
        Numeric(8, 2),
        default=Decimal("0.00"),
        server_default=text("0.00"),
        nullable=False,
    )
    credit_days: Mapped[Decimal] = mapped_column(
        Numeric(8, 2),
        default=Decimal("0.00"),
        server_default=text("0.00"),
        nullable=False,
    )
    converted_to_cash_days: Mapped[Decimal] = mapped_column(
        Numeric(8, 2),
        default=Decimal("0.00"),
        server_default=text("0.00"),
        nullable=False,
    )

    employee: Mapped[Employee] = relationship(lazy="joined")
    leave_type: Mapped[LeaveType] = relationship(lazy="joined")

    @property
    def calculated_available_credits(self) -> Decimal:
        """Return the raw ledger result before the zero-floor safeguard.

        This value is used only by the repair/audit workflow. Employee-facing
        balances always use ``available_credits``, which can never be below
        zero.
        """

        return (
            Decimal(self.beginning_credit_days)
            + Decimal(self.credit_days)
            + Decimal(self.adjustment_days)
            - Decimal(self.used_days)
            - Decimal(self.reserved_days)
            - Decimal(self.converted_to_cash_days)
        )

    @hybrid_property
    def available_credits(self) -> Decimal:
        """Return usable credits with a strict minimum of zero days."""

        return max(
            Decimal("0.00"),
            self.calculated_available_credits,
        )

    @hybrid_property
    def remaining_days(self) -> Decimal:
        """Backward-compatible alias used by existing leave workflows."""

        return self.available_credits
