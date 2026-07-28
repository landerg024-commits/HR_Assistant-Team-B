"""Role-specific database queries.

System roles are created by the seed process. Custom roles may be created
by administrators, but all role operations remain company-scoped.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.role import Role
from models.user import User
from repositories.base_repository import BaseRepository


class RoleRepository(BaseRepository[Role]):
    """Repository for company-scoped roles."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Role)

    def get_by_name(
        self,
        company_id: int,
        name: str,
    ) -> Role | None:
        """Return a role by name inside one company."""

        return self.session.scalar(
            select(Role).where(
                Role.company_id == company_id,
                Role.name == name,
            )
        )

    def list_all_for_company(
        self,
        company_id: int,
    ) -> list[Role]:
        """Return system and custom roles for administration."""

        statement = (
            select(Role)
            .where(Role.company_id == company_id)
            .order_by(
                Role.is_system_role.desc(),
                Role.name,
            )
        )

        return list(self.session.scalars(statement).all())

    def list_active(self, company_id: int) -> list[Role]:
        """Return active roles for user-account assignment."""

        statement = (
            select(Role)
            .where(
                Role.company_id == company_id,
                Role.is_active.is_(True),
            )
            .order_by(Role.name)
        )

        return list(self.session.scalars(statement).all())

    def count_assigned_users(
        self,
        *,
        company_id: int,
        role_id: int,
    ) -> int:
        """Count company users currently assigned to one role."""

        count = self.session.scalar(
            select(func.count(User.id)).where(
                User.company_id == company_id,
                User.role_id == role_id,
            )
        )

        return int(count or 0)

    def update_active_status(
        self,
        *,
        company_id: int,
        role_id: int,
        is_active: bool,
    ) -> Role | None:
        """Activate or deactivate one company-owned role."""

        role = self.get_by_id(
            record_id=role_id,
            company_id=company_id,
        )

        if role is None:
            return None

        role.is_active = is_active
        self.session.commit()
        self.session.refresh(role)

        return role
