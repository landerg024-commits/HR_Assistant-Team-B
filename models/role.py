"""Company-scoped role model for future access control."""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from models.company import Company
    from models.user import User


class Role(TimestampMixin, Base):
    """A role assigned to users inside one company."""

    __tablename__ = "roles"

    # The same role name may exist in another company,
    # but it must be unique inside the current company.
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "name",
            name="uq_roles_company_name",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))

    # System roles are seeded by the application.
    is_system_role: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    company: Mapped["Company"] = relationship(back_populates="roles")
    users: Mapped[list["User"]] = relationship(back_populates="role")
