"""v8.8.62 event allowance display and cash-conversion UI rules."""

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
from schemas.leave_schema import LeaveDecisionInput, LeaveRequestInput
from scripts.create_initial_data import seed_initial_data
from services.leave_service import LeaveService


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CapturingSender:
    """Collect outbound leave emails without network access."""

    def __init__(self) -> None:
        self.messages: list[OutboundEmail] = []

    def send(self, message: OutboundEmail) -> str:
        self.messages.append(message)
        return "captured"


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code="V8862",
        initial_company_name="Event Allowance Company",
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


def _employee(session, seed, *, gender: str) -> tuple[Employee, User]:
    user = User(
        company_id=seed["company"].id,
        role_id=seed["admin_user"].role_id,
        clearance=2,
        username=f"employee-{gender.lower()}",
        email=f"{gender.lower()}@example.com",
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
        employee_number=f"EMP-{gender.upper()}",
        first_name="Event",
        last_name="Employee",
        work_email=user.email,
        gender=gender,
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


def _rows(service: LeaveService, company_id: int, employee_id: int):
    return {
        row.leave_type.code: row
        for row in service.credit_table_rows(
            company_id=company_id,
            employee_id=employee_id,
            year=date.today().year,
        )
    }


def test_event_allowances_appear_in_available_credits_by_gender(
    tmp_path: Path,
) -> None:
    factory = _factory()
    with factory() as session:
        settings = _settings(tmp_path)
        seed = seed_initial_data(session, settings)
        seed["admin_employee"].work_email = "manager@example.com"
        male, _ = _employee(session, seed, gender="Male")
        female, _ = _employee(session, seed, gender="Female")
        service = LeaveService(
            session,
            settings=settings,
            email_sender=CapturingSender(),
        )

        male_rows = _rows(service, seed["company"].id, male.id)
        assert male_rows["EMERGENCY"].available_credits == Decimal("3.00")
        assert male_rows["HONEYMOON"].available_credits == Decimal("5.00")
        assert male_rows["MATERNITY"].available_credits == Decimal("0.00")
        assert male_rows["MATERNITY"].is_applicable is False
        assert male_rows["PATERNITY"].available_credits == Decimal("7.00")
        assert male_rows["PATERNITY"].is_applicable is True
        assert male_rows["BEREAVEMENT"].available_credits == Decimal("7.00")

        female_rows = _rows(service, seed["company"].id, female.id)
        assert female_rows["HONEYMOON"].available_credits == Decimal("5.00")
        assert female_rows["MATERNITY"].available_credits == Decimal("105.00")
        assert female_rows["MATERNITY"].is_applicable is True
        assert female_rows["PATERNITY"].available_credits == Decimal("0.00")
        assert female_rows["PATERNITY"].is_applicable is False
        assert female_rows["BEREAVEMENT"].available_credits == Decimal("7.00")


def test_approved_event_row_switches_to_actual_remaining_grant(
    tmp_path: Path,
) -> None:
    factory = _factory()
    with factory() as session:
        settings = _settings(tmp_path)
        seed = seed_initial_data(session, settings)
        seed["admin_employee"].work_email = "manager@example.com"
        employee, user = _employee(session, seed, gender="Female")
        service = LeaveService(
            session,
            settings=settings,
            email_sender=CapturingSender(),
        )
        balances = service.list_employee_balances(
            seed["company"].id,
            employee.id,
            date.today().year,
        )
        maternity = next(
            balance
            for balance in balances
            if balance.leave_type.code == "MATERNITY"
        )
        monday = _next_monday()

        submitted = service.submit_leave_request(
            LeaveRequestInput(
                company_id=seed["company"].id,
                employee_id=employee.id,
                requested_by_user_id=user.id,
                leave_type_id=maternity.leave_type_id,
                start_date=monday,
                end_date=monday + timedelta(days=1),
                reason="Qualifying maternity event",
            )
        )
        service.decide_leave_request(
            LeaveDecisionInput(
                company_id=seed["company"].id,
                request_id=submitted.request.id,
                manager_employee_id=seed["admin_employee"].id,
                manager_user_id=seed["admin_user"].id,
                decision="approve",
            )
        )

        rows = _rows(service, seed["company"].id, employee.id)
        assert rows["MATERNITY"].credit_days == Decimal("105.00")
        assert rows["MATERNITY"].reserved_days == Decimal("2.00")
        assert rows["MATERNITY"].available_credits == Decimal("103.00")


def test_only_sick_and_vacation_support_cash_conversion() -> None:
    assert LeaveService.supports_cash_conversion("VACATION") is True
    assert LeaveService.supports_cash_conversion("SICK") is True

    for code in (
        "EMERGENCY",
        "HONEYMOON",
        "MATERNITY",
        "PATERNITY",
        "BEREAVEMENT",
    ):
        assert LeaveService.supports_cash_conversion(code) is False

    employee_source = (
        PROJECT_ROOT / "ui/pages/user/leave_management_page.py"
    ).read_text(encoding="utf-8")
    admin_source = (
        PROJECT_ROOT / "ui/pages/admin/leave_management_page.py"
    ).read_text(encoding="utf-8")
    assert 'else "—"' in employee_source
    assert 'else "—"' in admin_source
