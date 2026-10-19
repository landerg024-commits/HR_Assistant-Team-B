"""Company business logic.

Services sit between the UI and repositories. They enforce validation and
business rules before database changes are made.
"""

from sqlalchemy.orm import Session

from repositories.company_repository import CompanyRepository
from schemas.company_schema import CompanyCreate


class CompanyService:
    """Create and manage companies."""

    def __init__(self, session: Session) -> None:
        self.repository = CompanyRepository(session)

    def create_company(self, values: CompanyCreate):
        """Create a company when its code does not already exist."""

        existing = self.repository.get_by_code(values.code)

        if existing is not None:
            raise ValueError(
                f"Company code '{values.code}' already exists."
            )

        return self.repository.create(values.model_dump())
