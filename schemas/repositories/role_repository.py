"""Role-specific database queries."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.role import Role
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
        """Find a role inside one company."""

        return self.session.scalar(
            select(Role).where(
                Role.company_id == company_id,
                Role.name == name,
            )
        )
