"""Department-specific repository queries."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.department import Department
from repositories.base_repository import BaseRepository


class DepartmentRepository(BaseRepository[Department]):
    """Repository for company-scoped departments."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Department)

    def get_by_name(
        self,
        company_id: int,
        name: str,
    ) -> Department | None:
        """Return a department by name inside a company."""

        return self.session.scalar(
            select(Department).where(
                Department.company_id == company_id,
                Department.name == name,
            )
        )
