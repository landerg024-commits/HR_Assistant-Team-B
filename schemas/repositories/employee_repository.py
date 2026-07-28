"""Employee-specific database queries."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.employee import Employee
from repositories.base_repository import BaseRepository


class EmployeeRepository(BaseRepository[Employee]):
    """Repository for company-scoped employee profiles."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Employee)

    def get_by_employee_number(
        self,
        company_id: int,
        employee_number: str,
    ) -> Employee | None:
        """Find an employee using the safe company-scoped identifier."""

        return self.session.scalar(
            select(Employee).where(
                Employee.company_id == company_id,
                Employee.employee_number == employee_number,
            )
        )

    def find_by_full_name(
        self,
        company_id: int,
        first_name: str,
        last_name: str,
    ) -> list[Employee]:
        """Return every employee matching a name.

        A list is returned because multiple employees may share the same name.
        """

        statement = select(Employee).where(
            Employee.company_id == company_id,
            Employee.first_name == first_name,
            Employee.last_name == last_name,
        )

        return list(self.session.scalars(statement).all())
