"""Repository for employee training checklist items."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from models.employee_training import EmployeeTraining
from repositories.base_repository import BaseRepository


class EmployeeTrainingRepository(
    BaseRepository[EmployeeTraining]
):
    """Company-scoped training checklist persistence."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, EmployeeTraining)

    def list_for_employee(
        self,
        *,
        company_id: int,
        employee_id: int,
    ) -> list[EmployeeTraining]:
        """Return training items in their display order."""

        statement = (
            select(EmployeeTraining)
            .where(
                EmployeeTraining.company_id == company_id,
                EmployeeTraining.employee_id == employee_id,
            )
            .order_by(
                EmployeeTraining.display_order,
                EmployeeTraining.id,
            )
        )

        return list(self.session.scalars(statement).all())

    def replace_for_employee(
        self,
        *,
        company_id: int,
        employee_id: int,
        items: list[dict[str, object]],
    ) -> list[EmployeeTraining]:
        """Replace the employee checklist with validated items."""

        self.session.execute(
            delete(EmployeeTraining).where(
                EmployeeTraining.company_id == company_id,
                EmployeeTraining.employee_id == employee_id,
            )
        )

        records = [
            EmployeeTraining(
                company_id=company_id,
                employee_id=employee_id,
                title=str(item["title"]),
                is_completed=bool(item["is_completed"]),
                display_order=index,
            )
            for index, item in enumerate(items)
        ]

        self.session.add_all(records)
        self.session.commit()

        return records
