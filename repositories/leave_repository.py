"""Company-scoped leave-management database queries."""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from models.employee import Employee
from models.leave_balance import LeaveBalance
from models.leave_credit_transaction import LeaveCreditTransaction
from models.leave_request import LeaveRequest
from models.leave_type import LeaveType
from repositories.base_repository import BaseRepository


class LeaveTypeRepository(BaseRepository[LeaveType]):
    """Queries for leave type settings."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, LeaveType)

    def list_company(self, company_id: int, *, active_only: bool = False) -> list[LeaveType]:
        statement = select(LeaveType).where(LeaveType.company_id == company_id)
        if active_only:
            statement = statement.where(LeaveType.is_active.is_(True))
        statement = statement.order_by(LeaveType.name)
        return list(self.session.scalars(statement).all())

    def get_by_code(self, company_id: int, code: str) -> LeaveType | None:
        return self.session.scalar(
            select(LeaveType).where(
                LeaveType.company_id == company_id,
                func.lower(LeaveType.code) == code.strip().lower(),
            )
        )

    def get_by_name(self, company_id: int, name: str) -> LeaveType | None:
        return self.session.scalar(
            select(LeaveType).where(
                LeaveType.company_id == company_id,
                func.lower(LeaveType.name) == name.strip().lower(),
            )
        )


class LeaveBalanceRepository(BaseRepository[LeaveBalance]):
    """Queries for employee leave balances."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, LeaveBalance)

    def get_balance(self, *, company_id: int, employee_id: int, leave_type_id: int, year: int) -> LeaveBalance | None:
        return self.session.scalar(
            select(LeaveBalance)
            .options(
                joinedload(
                    LeaveBalance.employee
                ).joinedload(
                    Employee.department
                ),
                joinedload(
                    LeaveBalance.employee
                ).joinedload(
                    Employee.manager
                ).joinedload(
                    Employee.user
                ),
                joinedload(
                    LeaveBalance.employee
                ).joinedload(
                    Employee.user
                ),
                joinedload(
                    LeaveBalance.leave_type
                ),
            )
            .where(
                LeaveBalance.company_id == company_id,
                LeaveBalance.employee_id == employee_id,
                LeaveBalance.leave_type_id == leave_type_id,
                LeaveBalance.year == year,
            )
        )

    def list_company_year(self, company_id: int, year: int) -> list[LeaveBalance]:
        statement = (
            select(LeaveBalance)
            .options(
                joinedload(
                    LeaveBalance.employee
                ).joinedload(
                    Employee.department
                ),
                joinedload(
                    LeaveBalance.employee
                ).joinedload(
                    Employee.manager
                ).joinedload(
                    Employee.user
                ),
                joinedload(
                    LeaveBalance.employee
                ).joinedload(
                    Employee.user
                ),
                joinedload(
                    LeaveBalance.leave_type
                ),
            )
            .join(Employee, Employee.id == LeaveBalance.employee_id)
            .where(LeaveBalance.company_id == company_id, LeaveBalance.year == year)
            .order_by(Employee.last_name, Employee.first_name, LeaveBalance.leave_type_id)
        )
        return list(self.session.scalars(statement).unique().all())

    def list_employee_year(self, company_id: int, employee_id: int, year: int) -> list[LeaveBalance]:
        statement = (
            select(LeaveBalance)
            .options(
                joinedload(
                    LeaveBalance.employee
                ).joinedload(
                    Employee.department
                ),
                joinedload(
                    LeaveBalance.employee
                ).joinedload(
                    Employee.manager
                ).joinedload(
                    Employee.user
                ),
                joinedload(
                    LeaveBalance.employee
                ).joinedload(
                    Employee.user
                ),
                joinedload(
                    LeaveBalance.leave_type
                ),
            )
            .where(
                LeaveBalance.company_id == company_id,
                LeaveBalance.employee_id == employee_id,
                LeaveBalance.year == year,
            )
            .order_by(LeaveBalance.leave_type_id)
        )
        return list(self.session.scalars(statement).unique().all())


class LeaveRequestRepository(BaseRepository[LeaveRequest]):
    """Queries for leave request monitoring and employee history."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, LeaveRequest)

    def list_company(
        self,
        company_id: int,
        year: int | None = None,
    ) -> list[LeaveRequest]:
        """Return company requests, optionally limited by leave year.

        A request is included when its leave period overlaps the selected
        calendar year. This also handles requests that cross December and
        January.
        """

        statement = (
            select(LeaveRequest)
            .options(
                joinedload(
                    LeaveRequest.employee
                ).joinedload(
                    Employee.department
                ),
                joinedload(
                    LeaveRequest.manager
                ).joinedload(
                    Employee.user
                ),
                joinedload(
                    LeaveRequest.employee
                ).joinedload(
                    Employee.user
                ),
                joinedload(LeaveRequest.leave_type),
                joinedload(LeaveRequest.fallback_leave_type),
            )
            .where(LeaveRequest.company_id == company_id)
        )

        if year is not None:
            year_start = date(int(year), 1, 1)
            year_end = date(int(year), 12, 31)
            statement = statement.where(
                LeaveRequest.end_date >= year_start,
                LeaveRequest.start_date <= year_end,
            )

        statement = statement.order_by(
            LeaveRequest.submitted_at.desc(),
            LeaveRequest.id.desc(),
        )

        return list(
            self.session.scalars(statement).unique().all()
        )

    def list_employee(self, company_id: int, employee_id: int) -> list[LeaveRequest]:
        statement = (
            select(LeaveRequest)
            .options(
                joinedload(
                    LeaveRequest.employee
                ).joinedload(
                    Employee.department
                ),
                joinedload(
                    LeaveRequest.employee
                ).joinedload(
                    Employee.user
                ),
                joinedload(
                    LeaveRequest.manager
                ).joinedload(
                    Employee.user
                ),
                joinedload(
                    LeaveRequest.leave_type
                ),
            )
            .where(
                LeaveRequest.company_id == company_id,
                LeaveRequest.employee_id == employee_id,
            )
            .order_by(LeaveRequest.submitted_at.desc(), LeaveRequest.id.desc())
        )
        return list(self.session.scalars(statement).unique().all())

    def get_with_details(self, company_id: int, request_id: int) -> LeaveRequest | None:
        statement = (
            select(LeaveRequest)
            .options(
                joinedload(LeaveRequest.employee).joinedload(Employee.department),
                joinedload(
                    LeaveRequest.manager
                ).joinedload(
                    Employee.user
                ),
                joinedload(
                    LeaveRequest.employee
                ).joinedload(
                    Employee.user
                ),
                joinedload(LeaveRequest.leave_type),
                joinedload(LeaveRequest.fallback_leave_type),
            )
            .where(LeaveRequest.company_id == company_id, LeaveRequest.id == request_id)
        )
        return self.session.scalar(statement)


    def list_pending_for_manager(
        self,
        *,
        company_id: int,
        manager_employee_id: int,
    ) -> list[LeaveRequest]:
        """Return requests awaiting this manager's decision."""

        statement = (
            select(LeaveRequest)
            .options(
                joinedload(
                    LeaveRequest.employee
                ).joinedload(
                    Employee.department
                ),
                joinedload(
                    LeaveRequest.employee
                ).joinedload(
                    Employee.user
                ),
                joinedload(
                    LeaveRequest.manager
                ).joinedload(
                    Employee.user
                ),
                joinedload(LeaveRequest.leave_type),
                joinedload(LeaveRequest.fallback_leave_type),
            )
            .where(
                LeaveRequest.company_id == company_id,
                LeaveRequest.manager_employee_id
                == manager_employee_id,
                LeaveRequest.status
                == "pending_manager_approval",
            )
            .order_by(
                LeaveRequest.submitted_at.asc(),
                LeaveRequest.id.asc(),
            )
        )

        return list(
            self.session.scalars(statement).unique().all()
        )

    def list_reviewed_for_manager(
        self,
        *,
        company_id: int,
        manager_employee_id: int,
    ) -> list[LeaveRequest]:
        """Return requests already reviewed by this manager."""

        statement = (
            select(LeaveRequest)
            .options(
                joinedload(
                    LeaveRequest.employee
                ).joinedload(
                    Employee.department
                ),
                joinedload(
                    LeaveRequest.employee
                ).joinedload(
                    Employee.user
                ),
                joinedload(
                    LeaveRequest.manager
                ).joinedload(
                    Employee.user
                ),
                joinedload(LeaveRequest.leave_type),
                joinedload(LeaveRequest.fallback_leave_type),
            )
            .where(
                LeaveRequest.company_id == company_id,
                LeaveRequest.manager_employee_id
                == manager_employee_id,
                LeaveRequest.status.in_(
                    (
                        "scheduled",
                        "approved",
                        "in_progress",
                        "completed",
                        "rejected",
                    )
                ),
            )
            .order_by(
                LeaveRequest.reviewed_at.desc(),
                LeaveRequest.id.desc(),
            )
        )

        return list(
            self.session.scalars(statement).unique().all()
        )

    def list_reconcilable(
        self,
        *,
        company_id: int,
        through_date: date,
    ) -> list[LeaveRequest]:
        """Return approved requests that may need date-based posting."""

        statement = (
            select(LeaveRequest)
            .options(
                joinedload(
                    LeaveRequest.employee
                ).joinedload(
                    Employee.department
                ),
                joinedload(
                    LeaveRequest.employee
                ).joinedload(
                    Employee.user
                ),
                joinedload(
                    LeaveRequest.manager
                ).joinedload(
                    Employee.user
                ),
                joinedload(LeaveRequest.leave_type),
                joinedload(LeaveRequest.fallback_leave_type),
            )
            .where(
                LeaveRequest.company_id == company_id,
                LeaveRequest.status.in_(
                    (
                        "scheduled",
                        "approved",
                        "in_progress",
                    )
                ),
                LeaveRequest.start_date <= through_date,
            )
            .order_by(
                LeaveRequest.start_date,
                LeaveRequest.id,
            )
        )

        return list(
            self.session.scalars(statement).unique().all()
        )

class LeaveCreditTransactionRepository(BaseRepository[LeaveCreditTransaction]):
    """Queries for immutable leave-credit history."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, LeaveCreditTransaction)

    def list_employee_year(self, company_id: int, employee_id: int, year: int) -> list[LeaveCreditTransaction]:
        statement = (
            select(LeaveCreditTransaction)
            .join(LeaveBalance, LeaveBalance.id == LeaveCreditTransaction.leave_balance_id)
            .where(
                LeaveCreditTransaction.company_id == company_id,
                LeaveCreditTransaction.employee_id == employee_id,
                LeaveBalance.year == year,
            )
            .order_by(LeaveCreditTransaction.created_at.desc(), LeaveCreditTransaction.id.desc())
        )
        return list(self.session.scalars(statement).all())
