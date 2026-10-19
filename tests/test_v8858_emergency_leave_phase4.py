"""Phase 4 Emergency Leave allowance and VL-deduction regression tests."""

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from config.settings import Settings
from database.base import Base
from integrations.email.email_sender import OutboundEmail
from models.employee import Employee
from models.user import User
from schemas.leave_schema import (
    LeaveCreditBalanceSetInput,
    LeaveDecisionInput,
    LeaveRequestInput,
)
from scripts.create_initial_data import seed_initial_data
from services.leave_service import LeaveService


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CapturingSender:
    """Collect outbound messages without network access."""

    def __init__(self) -> None:
        self.messages: list[OutboundEmail] = []

    def send(self, message: OutboundEmail) -> str:
        self.messages.append(message)
        return "captured"


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code="V8858",
        initial_company_name="Emergency Leave Company",
        initial_admin_username="manager",
        initial_admin_email="manager@example.com",
        initial_admin_password=SecretStr("Temporary123!"),
        initial_admin_employee_number="MGR-001",
        initial_admin_first_name="Mina",
        initial_admin_last_name="Manager",
        leave_attachment_dir=str(tmp_path / "leave_files"),
        password_reset_outbox_dir=str(tmp_path / "outbox"),
        password_reset_base_url="http://localhost:8501",
    )


def _factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _employee_with_login(session, seed) -> tuple[Employee, User]:
    user = User(
        company_id=seed["company"].id,
        role_id=seed["admin_user"].role_id,
        clearance=2,
        username="employee",
        email="employee@example.com",
        password_hash=seed["admin_user"].password_hash,
        is_active=True,
        must_change_password=False,
    )
    session.add(user)
    session.flush()

    employee = Employee(
        company_id=seed["company"].id,
        user_id=user.id,
        manager_id=seed["admin_employee"].id,
        employee_number="EMP-EL-001",
        first_name="Ella",
        last_name="Emergency",
        work_email="employee@example.com",
        employment_status="employed",
        hire_date=date(2020, 1, 1),
    )
    session.add(employee)
    session.commit()
    session.refresh(employee)
    return employee, user


def _next_monday() -> date:
    selected = date.today() + timedelta(days=10)
    while selected.weekday() != 0:
        selected += timedelta(days=1)
    return selected


def _balance(service, company_id: int, employee_id: int, code: str):
    return next(
        item
        for item in service.list_employee_balances(
            company_id,
            employee_id,
            date.today().year,
        )
        if item.leave_type.code == code
    )


def test_emergency_allowance_is_three_days_and_not_a_separate_credit(
    tmp_path: Path,
) -> None:
    factory = _factory()
    with factory() as session:
        settings = _settings(tmp_path)
        seed = seed_initial_data(session, settings)
        seed["admin_employee"].work_email = "manager@example.com"
        employee, _ = _employee_with_login(session, seed)
        service = LeaveService(
            session,
            settings=settings,
            email_sender=CapturingSender(),
        )

        emergency = _balance(
            service,
            seed["company"].id,
            employee.id,
            "EMERGENCY",
        )
        rows = service.credit_table_rows(
            company_id=seed["company"].id,
            employee_id=employee.id,
            year=date.today().year,
        )
        emergency_row = next(
            row for row in rows if row.leave_type.code == "EMERGENCY"
        )

        assert Decimal(emergency.allocated_days) == Decimal("0.00")
        assert Decimal(emergency.credit_days) == Decimal("0.00")
        assert emergency_row.used_days == Decimal("0.00")
        assert emergency_row.available_credits == Decimal("3.00")

        try:
            service.set_credit_balance(
                LeaveCreditBalanceSetInput(
                    company_id=seed["company"].id,
                    employee_id=employee.id,
                    leave_type_id=emergency.leave_type_id,
                    year=date.today().year,
                    new_remaining_days=Decimal("3.00"),
                    reason="Should not create standalone EL credits",
                    created_by_user_id=seed["admin_user"].id,
                )
            )
        except ValueError as error:
            assert "no independent credit balance" in str(error)
        else:
            raise AssertionError("Standalone Emergency Leave credit was accepted")


def test_emergency_approval_deducts_vl_and_tracks_own_allowance(
    tmp_path: Path,
) -> None:
    factory = _factory()
    with factory() as session:
        settings = _settings(tmp_path)
        seed = seed_initial_data(session, settings)
        seed["admin_employee"].work_email = "manager@example.com"
        employee, employee_user = _employee_with_login(session, seed)
        service = LeaveService(
            session,
            settings=settings,
            email_sender=CapturingSender(),
        )
        emergency = _balance(
            service,
            seed["company"].id,
            employee.id,
            "EMERGENCY",
        )
        vacation = _balance(
            service,
            seed["company"].id,
            employee.id,
            "VACATION",
        )
        starting_vl = Decimal(vacation.remaining_days)
        monday = _next_monday()
        tuesday = monday + timedelta(days=1)

        submitted = service.submit_leave_request(
            LeaveRequestInput(
                company_id=seed["company"].id,
                employee_id=employee.id,
                requested_by_user_id=employee_user.id,
                leave_type_id=emergency.leave_type_id,
                start_date=monday,
                end_date=tuesday,
                reason="Urgent family matter",
            )
        )
        assert Decimal(submitted.request.primary_credit_days) == Decimal("0.00")
        assert Decimal(submitted.request.fallback_credit_days) == Decimal("2.00")
        assert Decimal(submitted.request.lwop_days) == Decimal("0.00")
        assert submitted.request.fallback_leave_type.code == "VACATION"

        approved = service.decide_leave_request(
            LeaveDecisionInput(
                company_id=seed["company"].id,
                request_id=submitted.request.id,
                manager_employee_id=seed["admin_employee"].id,
                manager_user_id=seed["admin_user"].id,
                decision="approve",
            )
        )
        vacation_after_approval = service.balance_repository.get_balance(
            company_id=seed["company"].id,
            employee_id=employee.id,
            leave_type_id=vacation.leave_type_id,
            year=monday.year,
        )
        summary = service.emergency_allowance_summary(
            company_id=seed["company"].id,
            employee_id=employee.id,
            year=monday.year,
        )

        assert Decimal(vacation_after_approval.reserved_days) == Decimal("2.00")
        assert Decimal(vacation_after_approval.remaining_days) == starting_vl - Decimal("2.00")
        assert summary.used_days == Decimal("0.00")
        assert summary.reserved_days == Decimal("2.00")
        assert summary.remaining_days == Decimal("1.00")
        assert (
            service.allocation_breakdown(approved)
            == "2 Emergency Leave (deducted from Vacation Leave)"
        )

        service.reconcile_approved_leave(
            company_id=seed["company"].id,
            through_date=tuesday,
        )
        vacation_after_use = service.balance_repository.get_balance(
            company_id=seed["company"].id,
            employee_id=employee.id,
            leave_type_id=vacation.leave_type_id,
            year=monday.year,
        )
        summary_after_use = service.emergency_allowance_summary(
            company_id=seed["company"].id,
            employee_id=employee.id,
            year=monday.year,
        )
        row_after_use = next(
            row
            for row in service.credit_table_rows(
                company_id=seed["company"].id,
                employee_id=employee.id,
                year=monday.year,
            )
            if row.leave_type.code == "EMERGENCY"
        )

        assert Decimal(vacation_after_use.reserved_days) == Decimal("0.00")
        assert Decimal(vacation_after_use.used_days) == Decimal("2.00")
        assert summary_after_use.used_days == Decimal("2.00")
        assert summary_after_use.remaining_days == Decimal("1.00")
        assert row_after_use.used_days == Decimal("2.00")
        assert row_after_use.available_credits == Decimal("1.00")


def test_second_emergency_request_only_uses_remaining_allowance(
    tmp_path: Path,
) -> None:
    factory = _factory()
    with factory() as session:
        settings = _settings(tmp_path)
        seed = seed_initial_data(session, settings)
        seed["admin_employee"].work_email = "manager@example.com"
        employee, employee_user = _employee_with_login(session, seed)
        service = LeaveService(
            session,
            settings=settings,
            email_sender=CapturingSender(),
        )
        emergency = _balance(
            service,
            seed["company"].id,
            employee.id,
            "EMERGENCY",
        )
        monday = _next_monday()

        first = service.submit_leave_request(
            LeaveRequestInput(
                company_id=seed["company"].id,
                employee_id=employee.id,
                requested_by_user_id=employee_user.id,
                leave_type_id=emergency.leave_type_id,
                start_date=monday,
                end_date=monday + timedelta(days=1),
                reason="First emergency",
            )
        )
        service.decide_leave_request(
            LeaveDecisionInput(
                company_id=seed["company"].id,
                request_id=first.request.id,
                manager_employee_id=seed["admin_employee"].id,
                manager_user_id=seed["admin_user"].id,
                decision="approve",
            )
        )

        second = service.submit_leave_request(
            LeaveRequestInput(
                company_id=seed["company"].id,
                employee_id=employee.id,
                requested_by_user_id=employee_user.id,
                leave_type_id=emergency.leave_type_id,
                start_date=monday + timedelta(days=2),
                end_date=monday + timedelta(days=3),
                reason="Second emergency",
            )
        )
        approved_second = service.decide_leave_request(
            LeaveDecisionInput(
                company_id=seed["company"].id,
                request_id=second.request.id,
                manager_employee_id=seed["admin_employee"].id,
                manager_user_id=seed["admin_user"].id,
                decision="approve",
            )
        )
        summary = service.emergency_allowance_summary(
            company_id=seed["company"].id,
            employee_id=employee.id,
            year=monday.year,
        )

        assert Decimal(approved_second.fallback_credit_days) == Decimal("1.00")
        assert Decimal(approved_second.lwop_days) == Decimal("1.00")
        assert summary.remaining_days == Decimal("0.00")
        assert summary.reserved_days == Decimal("3.00")
        assert (
            service.allocation_breakdown(approved_second)
            == "1 Emergency Leave (deducted from Vacation Leave) + 1 LWOP"
        )


def test_phase4_ui_explains_el_is_inside_vacation_leave() -> None:
    admin_source = (
        PROJECT_ROOT / "ui/pages/admin/leave_management_page.py"
    ).read_text(encoding="utf-8")
    employee_source = (
        PROJECT_ROOT / "ui/pages/user/leave_management_page.py"
    ).read_text(encoding="utf-8")

    assert "Emergency Leave is not editable as a separate credit" in admin_source
    assert "maximum three-day annual allowance" in employee_source
    assert "deducted from Vacation Leave" in employee_source
