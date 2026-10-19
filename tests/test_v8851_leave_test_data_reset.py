"""Regression tests for the leave-only development data reset utility."""

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from pydantic import SecretStr
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from config.settings import Settings
from database.base import Base
from models.employee import Employee
from models.leave_balance import LeaveBalance
from models.leave_credit_transaction import LeaveCreditTransaction
from models.leave_request import LeaveRequest
from models.leave_type import LeaveType
from models.notification import Notification
from models.user import User
from schemas.leave_schema import LeaveCreditAdjustmentInput, LeaveRequestInput
from scripts.create_initial_data import seed_initial_data
from scripts.reset_leave_test_data import reset_company_leave_data
from services.leave_service import LeaveService


class CapturingSender:
    """Email sender replacement used by the leave request test."""

    def send(self, _message) -> str:
        return "captured"


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code="RESET",
        initial_company_name="Reset Company",
        initial_admin_username="admin",
        initial_admin_email="admin.reset@example.com",
        initial_admin_password=SecretStr("Temporary123!"),
        initial_admin_employee_number="ADMIN-001",
        initial_admin_first_name="System",
        initial_admin_last_name="Administrator",
        leave_attachment_dir=str(tmp_path / "leave_files"),
        password_reset_outbox_dir=str(tmp_path / "outbox"),
    )


def test_leave_reset_preserves_master_data_and_recreates_clean_balances(
    tmp_path: Path,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = _settings(tmp_path)

    with factory() as session:
        seed = seed_initial_data(session, settings)
        manager = seed["admin_employee"]
        manager.work_email = "manager@reset.test"
        manager.user_id = None
        employee = Employee(
            company_id=seed["company"].id,
            department_id=manager.department_id,
            manager_id=manager.id,
            user_id=seed["admin_user"].id,
            employee_number="EMP-RESET",
            first_name="Test",
            last_name="Employee",
            work_email="employee@reset.test",
            job_title="Staff",
            employment_status="employed",
        )
        session.add(employee)
        session.commit()

        service = LeaveService(
            session,
            settings=settings,
            email_sender=CapturingSender(),
        )
        vacation = next(
            balance
            for balance in service.list_employee_balances(
                seed["company"].id,
                employee.id,
            )
            if balance.leave_type.code == "VACATION"
        )
        service.adjust_credit(
            LeaveCreditAdjustmentInput(
                company_id=seed["company"].id,
                employee_id=employee.id,
                leave_type_id=vacation.leave_type_id,
                year=date.today().year,
                adjustment_days=Decimal("2.00"),
                reason="Temporary test credit",
                created_by_user_id=seed["admin_user"].id,
            )
        )

        start = date.today() + timedelta(days=10)
        while start.weekday() >= 5:
            start += timedelta(days=1)
        service.submit_leave_request(
            LeaveRequestInput(
                company_id=seed["company"].id,
                employee_id=employee.id,
                requested_by_user_id=seed["admin_user"].id,
                leave_type_id=vacation.leave_type_id,
                start_date=start,
                end_date=start,
                reason="Temporary test request",
            )
        )

        result = reset_company_leave_data(
            session,
            company=seed["company"],
            settings=settings,
            recreate_current_year=True,
        )

        assert result.requests_deleted == 1
        assert result.balances_deleted > 0
        assert result.transactions_deleted > 0
        assert result.notifications_deleted > 0

        assert session.scalar(select(func.count(LeaveRequest.id))) == 0
        assert session.scalar(select(func.count(Notification.id))) == 0

        clean_balances = list(
            session.scalars(
                select(LeaveBalance).where(
                    LeaveBalance.company_id == seed["company"].id,
                    LeaveBalance.year == date.today().year,
                )
            ).all()
        )
        assert clean_balances
        assert all(Decimal(item.used_days) == Decimal("0.00") for item in clean_balances)
        assert all(Decimal(item.reserved_days) == Decimal("0.00") for item in clean_balances)
        assert all(Decimal(item.adjustment_days) == Decimal("0.00") for item in clean_balances)
        assert all(
            Decimal(item.converted_to_cash_days) == Decimal("0.00")
            for item in clean_balances
        )

        # Master data and configured leave types must remain intact.
        assert session.get(Employee, employee.id) is not None
        assert session.get(User, seed["admin_user"].id) is not None
        assert session.scalar(select(func.count(LeaveType.id))) >= 8
        assert session.scalar(select(func.count(LeaveCreditTransaction.id))) > 0
