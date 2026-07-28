"""Company-scoped department model."""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from models.company import Company
    from models.employee import Employee


class Department(TimestampMixin, Base):
    """An organizational department owned by one company."""

    __tablename__ = "departments"

    # Department names are unique only within the same company.
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "name",
            name="uq_departments_company_name",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    code: Mapped[str | None] = mapped_column(String(50))

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    company: Mapped["Company"] = relationship(
        back_populates="departments"
    )
    employees: Mapped[list["Employee"]] = relationship(
        back_populates="department"
    )
