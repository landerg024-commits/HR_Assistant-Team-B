"""Role business logic."""

from sqlalchemy.orm import Session

from repositories.role_repository import RoleRepository
from schemas.role_schema import RoleCreate


class RoleService:
    """Create or retrieve company-scoped roles."""

    def __init__(self, session: Session) -> None:
        self.repository = RoleRepository(session)

    def get_or_create_role(self, values: RoleCreate):
        """Return an existing role or create it once.

        The Boolean return value tells seed scripts whether a row was created.
        """

        existing = self.repository.get_by_name(
            values.company_id,
            values.name,
        )

        if existing is not None:
            return existing, False

        return (
            self.repository.create(values.model_dump()),
            True,
        )
