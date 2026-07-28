"""One training checklist item linked to an employee.

Training items are stored as separate rows for reliable editing, searching,
and future reporting. The Employees table combines them into one checklist
cell for display.
"""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from models.company import Company
    from models.employee import Employee


class EmployeeTraining(TimestampMixin, Base):
    """A company-scoped training checklist item."""

    __tablename__ = "employee_trainings"

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

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    is_completed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    display_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    company: Mapped["Company"] = relationship(
        back_populates="employee_trainings"
    )

    employee: Mapped["Employee"] = relationship(
        back_populates="trainings"
    )
