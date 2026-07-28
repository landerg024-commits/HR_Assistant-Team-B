"""Company-specific database queries.

Company code is the stable tenant identifier. Company name may change,
but the code should remain unchanged after company creation.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.company import Company
from repositories.base_repository import BaseRepository


class CompanyRepository(BaseRepository[Company]):
    """Repository for company records."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Company)

    def get_by_code(self, code: str) -> Company | None:
        """Return a company using its unique stable code."""

        return self.session.scalar(
            select(Company).where(Company.code == code)
        )

    def update_name(
        self,
        *,
        company_id: int,
        name: str,
    ) -> Company | None:
        """Update the display name without changing the company code."""

        company = self.get_by_id(company_id)

        if company is None:
            return None

        company.name = name
        self.session.commit()
        self.session.refresh(company)

        return company


    def update_theme_color(
        self,
        *,
        company_id: int,
        primary_color: str,
    ) -> Company | None:
        """Update only the company's primary accent color."""

        company = self.get_by_id(company_id)

        if company is None:
            return None

        company.theme_primary_color = primary_color
        self.session.commit()
        self.session.refresh(company)

        return company
