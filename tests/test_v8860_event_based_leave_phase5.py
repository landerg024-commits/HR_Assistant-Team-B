"""Phase 5 event-based leave entitlement regression tests."""

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from pydantic import SecretStr
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from config.settings import Settings
from database.base import Base
from integrations.email.email_sender import OutboundEmail
from models.employee import Employee
from models.leave_credit_transaction import LeaveCreditTransaction
from models.user import User
from schemas.leave_schema import (
    LeaveCreditBalanceSetInput,
    LeaveDecisionInput,
    LeaveRequestInput,
)
from scripts.create_initial_data import seed_initial_data
from services.leave_service import (
    EVENT_LEAVE_GRANT_TRANSACTION,
    LeaveService,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CapturingSender:
    """Collect outbound messages without sending network email."""

    def __init__(self) -> None:
        self.messages: list[OutboundEmail] = []

    def send(self, message: OutboundEmail) -> str:
        self.messages.append(message)
        return "captured"


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code="V8860",
        initial_company_name="Event Leave Company",
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


def _employee_with_login(
    session,
    seed,
    *,
    gender: str = "Male",
) -> tuple[Employee, User]:
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
        employee_number="EMP-EVENT-001",
        first_name="Evan",
        last_name="Event",
        work_email="employee@example.com",
        gender=gender,
        employment_status="employed",
        hire_date=date(2020, 1, 1),
    )
    session.add(employee)
    session.commit()
    session.refresh(employee)
    return employee, user


def _next_monday(offset_days: int = 10) -> date:
    selected = date.today() + timedelta(days=offset_days)
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


def _submit(
    service: LeaveService,
    *,
    seed,
    employee: Employee,
    employee_user: User,
    code: str,
    start_date: date,
    end_date: date,
):
    leave_type = _balance(
        service,
        seed["company"].id,
        employee.id,
        code,
    ).leave_type
    return service.submit_leave_request(
        LeaveRequestInput(
            company_id=seed["company"].id,
            employee_id=employee.id,
            requested_by_user_id=employee_user.id,
            leave_type_id=leave_type.id,
            start_date=start_date,
            end_date=end_date,
            reason=f"Qualifying {leave_type.name} event",
        )
    )


def _approve(service: LeaveService, *, seed, request_id: int):
    return service.decide_leave_request(
        LeaveDecisionInput(
            company_id=seed["company"].id,
            request_id=request_id,
            manager_employee_id=seed["admin_employee"].id,
            manager_user_id=seed["admin_user"].id,
            decision="approve",
        )
    )


def test_honeymoon_is_five_days_and_one_time(tmp_path: Path) -> None:
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
        monday = _next_monday()

        submitted = _submit(
            service,
            seed=seed,
            employee=employee,
            employee_user=employee_user,
            code="HONEYMOON",
            start_date=monday,
            end_date=monday + timedelta(days=7),
        )
        assert Decimal(submitted.request.primary_credit_days) == Decimal("5.00")
        assert Decimal(submitted.request.lwop_days) == Decimal("1.00")

        approved = _approve(
            service,
            seed=seed,
            request_id=submitted.request.id,
        )
        balance = _balance(
            service,
            seed["company"].id,
            employee.id,
            "HONEYMOON",
        )

        assert Decimal(balance.credit_days) == Decimal("5.00")
        assert Decimal(balance.reserved_days) == Decimal("5.00")
        assert Decimal(balance.available_credits) == Decimal("0.00")
        assert Decimal(approved.primary_credit_days) == Decimal("5.00")
        assert Decimal(approved.lwop_days) == Decimal("1.00")

        try:
            _submit(
                service,
                seed=seed,
                employee=employee,
                employee_user=employee_user,
                code="HONEYMOON",
                start_date=monday + timedelta(days=14),
                end_date=monday + timedelta(days=14),
            )
        except ValueError as error:
            assert "one-time five-day benefit" in str(error)
        else:
            raise AssertionError("A second Honeymoon Leave request was accepted")


def test_maternity_grants_105_only_after_manager_approval(tmp_path: Path) -> None:
    factory = _factory()
    with factory() as session:
        settings = _settings(tmp_path)
        seed = seed_initial_data(session, settings)
        seed["admin_employee"].work_email = "manager@example.com"
        employee, employee_user = _employee_with_login(
            session, seed, gender="Female"
        )
        service = LeaveService(
            session,
            settings=settings,
            email_sender=CapturingSender(),
        )
        monday = _next_monday()

        submitted = _submit(
            service,
            seed=seed,
            employee=employee,
            employee_user=employee_user,
            code="MATERNITY",
            start_date=monday,
            end_date=monday + timedelta(days=1),
        )
        before = _balance(
            service,
            seed["company"].id,
            employee.id,
            "MATERNITY",
        )
        assert Decimal(before.credit_days) == Decimal("0.00")
        assert Decimal(submitted.request.primary_credit_days) == Decimal("2.00")

        _approve(service, seed=seed, request_id=submitted.request.id)
        after = _balance(
            service,
            seed["company"].id,
            employee.id,
            "MATERNITY",
        )
        grant_count = session.scalar(
            select(func.count(LeaveCreditTransaction.id)).where(
                LeaveCreditTransaction.leave_request_id
                == submitted.request.id,
                LeaveCreditTransaction.transaction_type
                == EVENT_LEAVE_GRANT_TRANSACTION,
            )
        )

        assert Decimal(after.credit_days) == Decimal("105.00")
        assert Decimal(after.reserved_days) == Decimal("2.00")
        assert Decimal(after.available_credits) == Decimal("103.00")
        assert grant_count == 1


def test_paternity_adds_seven_days_for_each_approved_event(tmp_path: Path) -> None:
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
        monday = _next_monday()

        for offset in (0, 7):
            submitted = _submit(
                service,
                seed=seed,
                employee=employee,
                employee_user=employee_user,
                code="PATERNITY",
                start_date=monday + timedelta(days=offset),
                end_date=monday + timedelta(days=offset),
            )
            _approve(service, seed=seed, request_id=submitted.request.id)

        balance = _balance(
            service,
            seed["company"].id,
            employee.id,
            "PATERNITY",
        )
        assert Decimal(balance.credit_days) == Decimal("14.00")
        assert Decimal(balance.reserved_days) == Decimal("2.00")
        assert Decimal(balance.available_credits) == Decimal("12.00")


def test_bereavement_caps_one_event_at_seven_days(tmp_path: Path) -> None:
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
        monday = _next_monday()

        submitted = _submit(
            service,
            seed=seed,
            employee=employee,
            employee_user=employee_user,
            code="BEREAVEMENT",
            start_date=monday,
            end_date=monday + timedelta(days=9),
        )
        approved = _approve(
            service,
            seed=seed,
            request_id=submitted.request.id,
        )

        assert Decimal(approved.primary_credit_days) == Decimal("7.00")
        assert Decimal(approved.lwop_days) == Decimal("1.00")
        assert service.allocation_breakdown(approved) == (
            "7 Bereavement Leave + 1 LWOP"
        )


def test_rejected_event_request_does_not_create_credit(tmp_path: Path) -> None:
    factory = _factory()
    with factory() as session:
        settings = _settings(tmp_path)
        seed = seed_initial_data(session, settings)
        seed["admin_employee"].work_email = "manager@example.com"
        employee, employee_user = _employee_with_login(
            session, seed, gender="Female"
        )
        service = LeaveService(
            session,
            settings=settings,
            email_sender=CapturingSender(),
        )
        monday = _next_monday()

        submitted = _submit(
            service,
            seed=seed,
            employee=employee,
            employee_user=employee_user,
            code="MATERNITY",
            start_date=monday,
            end_date=monday,
        )
        service.decide_leave_request(
            LeaveDecisionInput(
                company_id=seed["company"].id,
                request_id=submitted.request.id,
                manager_employee_id=seed["admin_employee"].id,
                manager_user_id=seed["admin_user"].id,
                decision="reject",
            )
        )
        balance = _balance(
            service,
            seed["company"].id,
            employee.id,
            "MATERNITY",
        )
        assert Decimal(balance.credit_days) == Decimal("0.00")


def test_event_leave_credits_cannot_be_manually_set(tmp_path: Path) -> None:
    factory = _factory()
    with factory() as session:
        settings = _settings(tmp_path)
        seed = seed_initial_data(session, settings)
        employee, _ = _employee_with_login(session, seed)
        service = LeaveService(session, settings=settings)
        maternity = _balance(
            service,
            seed["company"].id,
            employee.id,
            "MATERNITY",
        )

        try:
            service.set_credit_balance(
                LeaveCreditBalanceSetInput(
                    company_id=seed["company"].id,
                    employee_id=employee.id,
                    leave_type_id=maternity.leave_type_id,
                    year=date.today().year,
                    new_remaining_days=Decimal("105.00"),
                    reason="Manual event credit should be blocked",
                    created_by_user_id=seed["admin_user"].id,
                )
            )
        except ValueError as error:
            assert "qualifying event request" in str(error)
        else:
            raise AssertionError("Manual event leave credit was accepted")


def test_phase5_ui_explains_event_based_entitlements() -> None:
    employee_source = (
        PROJECT_ROOT / "ui/pages/user/leave_management_page.py"
    ).read_text(encoding="utf-8")
    admin_source = (
        PROJECT_ROOT / "ui/pages/admin/leave_management_page.py"
    ).read_text(encoding="utf-8")

    assert "Honeymoon 5" in employee_source
    assert "Maternity 105" in employee_source
    assert "Paternity 7" in employee_source
    assert "Bereavement 7" in employee_source
    assert "per approved event" in employee_source
    assert "not manually editable" in admin_source


def test_maternity_and_paternity_gender_are_enforced_on_submission(
    tmp_path: Path,
) -> None:
    factory = _factory()
    with factory() as session:
        settings = _settings(tmp_path)
        seed = seed_initial_data(session, settings)
        seed["admin_employee"].work_email = "manager@example.com"
        male_employee, male_user = _employee_with_login(
            session, seed, gender="Male"
        )
        service = LeaveService(
            session,
            settings=settings,
            email_sender=CapturingSender(),
        )
        monday = _next_monday()

        try:
            _submit(
                service,
                seed=seed,
                employee=male_employee,
                employee_user=male_user,
                code="MATERNITY",
                start_date=monday,
                end_date=monday,
            )
        except ValueError as error:
            assert "Female" in str(error)
        else:
            raise AssertionError("Male employee submitted Maternity Leave")

        male_employee.gender = "Female"
        session.commit()
        try:
            _submit(
                service,
                seed=seed,
                employee=male_employee,
                employee_user=male_user,
                code="PATERNITY",
                start_date=monday,
                end_date=monday,
            )
        except ValueError as error:
            assert "Male" in str(error)
        else:
            raise AssertionError("Female employee submitted Paternity Leave")


def test_gender_is_rechecked_before_manager_approval(tmp_path: Path) -> None:
    factory = _factory()
    with factory() as session:
        settings = _settings(tmp_path)
        seed = seed_initial_data(session, settings)
        seed["admin_employee"].work_email = "manager@example.com"
        employee, employee_user = _employee_with_login(
            session, seed, gender="Female"
        )
        service = LeaveService(
            session,
            settings=settings,
            email_sender=CapturingSender(),
        )
        monday = _next_monday()
        submitted = _submit(
            service,
            seed=seed,
            employee=employee,
            employee_user=employee_user,
            code="MATERNITY",
            start_date=monday,
            end_date=monday,
        )

        employee.gender = "Male"
        session.commit()
        try:
            _approve(
                service,
                seed=seed,
                request_id=submitted.request.id,
            )
        except ValueError as error:
            assert "Female" in str(error)
        else:
            raise AssertionError("Invalid Maternity approval was accepted")

        request = service.request_repository.get_with_details(
            seed["company"].id,
            submitted.request.id,
        )
        assert request.status == "pending_manager_approval"


def test_event_allowances_use_available_credits_without_extra_column() -> None:
    assert LeaveService.leave_entitlement_display("HONEYMOON") == "5 one-time"
    assert LeaveService.leave_entitlement_display("MATERNITY") == (
        "105 per event · Female"
    )
    assert LeaveService.leave_entitlement_display("PATERNITY") == (
        "7 per event · Male"
    )
    assert LeaveService.leave_entitlement_display("BEREAVEMENT") == (
        "7 per event"
    )

    employee_source = (
        PROJECT_ROOT / "ui/pages/user/leave_management_page.py"
    ).read_text(encoding="utf-8")
    admin_source = (
        PROJECT_ROOT / "ui/pages/admin/leave_management_page.py"
    ).read_text(encoding="utf-8")

    assert '"Entitlement": LeaveService.leave_entitlement_display' not in (
        employee_source
    )
    assert '"Entitlement": LeaveService.leave_entitlement_display' not in (
        admin_source
    )
    assert '"Available Credits"' in employee_source
    assert '"Available Credits"' in admin_source
    assert "supports_cash_conversion" in employee_source
    assert "supports_cash_conversion" in admin_source
    assert "is_event_leave_gender_eligible" in employee_source
