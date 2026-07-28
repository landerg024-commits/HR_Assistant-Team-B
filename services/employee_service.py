"""Employee-profile business logic."""

from sqlalchemy.orm import Session

from repositories.employee_repository import EmployeeRepository
from schemas.user_schema import EmployeeCreate


class EmployeeService:
    """Create employees while enforcing the correct unique identifier."""

    def __init__(self, session: Session) -> None:
        self.repository = EmployeeRepository(session)

    def create_employee(self, values: EmployeeCreate):
        """Create an employee.

        Employee number must be unique inside the company.
        Full name is intentionally allowed to duplicate.
        """

        existing = self.repository.get_by_employee_number(
            values.company_id,
            values.employee_number,
        )

        if existing is not None:
            raise ValueError(
                f"Employee number '{values.employee_number}' "
                "already exists inside this company."
            )

        payload = values.model_dump()

        # Convert validated EmailStr into a normal string for SQLAlchemy.
        if payload.get("work_email") is not None:
            payload["work_email"] = str(payload["work_email"])

        return self.repository.create(payload)
