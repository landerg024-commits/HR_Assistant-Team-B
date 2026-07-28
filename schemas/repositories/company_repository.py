"""Company-specific database queries."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.company import Company
from repositories.base_repository import BaseRepository


class CompanyRepository(BaseRepository[Company]):
    """Repository for Company records."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Company)

    def get_by_code(self, code: str) -> Company | None:
        """Find a company using its stable unique code."""

        return self.session.scalar(
            select(Company).where(Company.code == code)
        )
