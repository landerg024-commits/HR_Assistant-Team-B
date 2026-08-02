"""Company model.

A company is the tenant boundary of the application. Every company-scoped
record must contain company_id so data from different companies cannot mix.
"""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.constants import DEFAULT_COMPANY_THEME_COLOR
from database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from models.department import Department
    from models.employee import Employee
    from models.employee_training import EmployeeTraining
    from models.role import Role
    from models.user import User


class Company(TimestampMixin, Base):
    """A company or organization using the HR Assistant."""

    __tablename__ = "companies"

    # Primary database identifier.
    id: Mapped[int] = mapped_column(primary_key=True)

    # Stable company code used in configuration, imports, and integrations.
    code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    # Company-specific primary accent used across both portals.
    theme_primary_color: Mapped[str] = mapped_column(
        String(7),
        default=DEFAULT_COMPANY_THEME_COLOR,
        server_default=DEFAULT_COMPANY_THEME_COLOR,
        nullable=False,
    )

    # Canonical company-scoped logo filename stored under the private
    # company-logo upload directory. The file is never served publicly.
    logo_filename: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Deleting a company also removes its owned records.
    users: Mapped[list["User"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )
    roles: Mapped[list["Role"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )
    departments: Mapped[list["Department"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )
    employees: Mapped[list["Employee"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )
    employee_trainings: Mapped[list["EmployeeTraining"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )
