"""Employee profile model.

Important design rule:
Full names are NOT unique. Two employees may have exactly the same name.
The safe identifier is employee_number inside a company.
"""

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from models.company import Company
    from models.department import Department
    from models.user import User


class Employee(TimestampMixin, Base):
    """A company-scoped employee profile."""

    __tablename__ = "employees"

    __table_args__ = (
        # Employee number must be unique inside one company.
        UniqueConstraint(
            "company_id",
            "employee_number",
            name="uq_employees_company_employee_number",
        ),
        # One user account can link to only one employee profile.
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

    # Optional until a login account is assigned.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )

    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"),
        index=True,
    )

    # Self-reference used for manager/direct-report relationships.
    manager_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"),
        index=True,
    )

    employee_number: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
    )

    # Name fields are stored separately for sorting and filtering.
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    suffix: Mapped[str | None] = mapped_column(String(30))

    work_email: Mapped[str | None] = mapped_column(String(255))
    job_title: Mapped[str | None] = mapped_column(String(150))

    employment_status: Mapped[str] = mapped_column(
        String(50),
        default="active",
        nullable=False,
    )

    hire_date: Mapped[date | None] = mapped_column(Date)

    company: Mapped["Company"] = relationship(back_populates="employees")
    user: Mapped["User | None"] = relationship(back_populates="employee")
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

    @property
    def full_name(self) -> str:
        """Build a display name from available name fields.

        This property is for display only and must never be used as a unique
        database identifier.
        """

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
