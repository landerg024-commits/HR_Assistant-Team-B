"""Department-specific database queries.

All queries include company_id to preserve tenant isolation.
"""

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
        """Return a department by name inside one company."""

        return self.session.scalar(
            select(Department).where(
                Department.company_id == company_id,
                Department.name == name,
            )
        )

    def get_by_code(
        self,
        company_id: int,
        code: str,
    ) -> Department | None:
        """Return a department by code inside one company."""

        return self.session.scalar(
            select(Department).where(
                Department.company_id == company_id,
                Department.code == code,
            )
        )

    def list_all_for_company(
        self,
        company_id: int,
    ) -> list[Department]:
        """Return active and inactive departments for administration."""

        statement = (
            select(Department)
            .where(Department.company_id == company_id)
            .order_by(
                Department.is_active.desc(),
                Department.name,
            )
        )

        return list(self.session.scalars(statement).all())

    def list_active(
        self,
        company_id: int,
    ) -> list[Department]:
        """Return active departments for employee assignment forms."""

        statement = (
            select(Department)
            .where(
                Department.company_id == company_id,
                Department.is_active.is_(True),
            )
            .order_by(Department.name)
        )

        return list(self.session.scalars(statement).all())

    def update_active_status(
        self,
        *,
        company_id: int,
        department_id: int,
        is_active: bool,
    ) -> Department | None:
        """Activate or deactivate one company-owned department."""

        department = self.get_by_id(
            record_id=department_id,
            company_id=company_id,
        )

        if department is None:
            return None

        department.is_active = is_active
        self.session.commit()
        self.session.refresh(department)

        return department
