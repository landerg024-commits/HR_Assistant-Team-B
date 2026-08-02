"""Employee master-record model.

Full names are not unique. Employee number is the stable company-scoped
identifier. Login data remains in ``users`` while training checklist items
remain in ``employee_trainings``.
"""

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from models.company import Company
    from models.department import Department
    from models.employee_training import EmployeeTraining
    from models.user import User


class Employee(TimestampMixin, Base):
    """A company-scoped employee master record."""

    __tablename__ = "employees"

    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "employee_number",
            name="uq_employees_company_employee_number",
        ),
        UniqueConstraint(
            "user_id",
            name="uq_employees_user_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )

    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"),
        index=True,
    )

    manager_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"),
        index=True,
    )

    employee_number: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
    )

    first_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    middle_name: Mapped[str | None] = mapped_column(
        String(100)
    )
    last_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    suffix: Mapped[str | None] = mapped_column(
        String(30)
    )

    work_email: Mapped[str | None] = mapped_column(
        String(255)
    )
    telephone_mobile_no: Mapped[str | None] = mapped_column(
        String(50)
    )
    job_title: Mapped[str | None] = mapped_column(
        String(150)
    )

    # User-facing values are limited to employed and resigned.
    employment_status: Mapped[str] = mapped_column(
        String(50),
        default="employed",
        nullable=False,
    )

    hire_date: Mapped[date | None] = mapped_column(Date)

    company: Mapped["Company"] = relationship(
        back_populates="employees"
    )
    user: Mapped["User | None"] = relationship(
        back_populates="employee"
    )
    department: Mapped["Department | None"] = relationship(
        back_populates="employees"
    )

    manager: Mapped["Employee | None"] = relationship(
        remote_side="Employee.id",
        back_populates="direct_reports",
    )
    direct_reports: Mapped[list["Employee"]] = relationship(
        back_populates="manager",
    )

    trainings: Mapped[list["EmployeeTraining"]] = relationship(
        back_populates="employee",
        cascade="all, delete-orphan",
        order_by="EmployeeTraining.display_order",
    )

    @property
    def full_name(self) -> str:
        """Build the display name without storing duplicate full-name data."""

        name_parts = [
            self.first_name,
            self.middle_name,
            self.last_name,
            self.suffix,
        ]

        return " ".join(
            part.strip()
            for part in name_parts
            if part and part.strip()
        )
