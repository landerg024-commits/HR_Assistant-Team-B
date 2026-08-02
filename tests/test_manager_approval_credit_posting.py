"""Manager approval, handover plan, and date-posting tests."""

from datetime import date, datetime, timedelta, timezone
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
    LeaveDecisionInput,
    LeaveRequestInput,
)
from scripts.create_initial_data import seed_initial_data
from services.leave_service import LeaveService


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CapturingSender:
    """Collect email messages without network access."""

    def __init__(self) -> None:
        self.messages: list[OutboundEmail] = []

    def send(self, message: OutboundEmail) -> str:
        self.messages.append(message)
        return "captured"


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code="APPROVAL",
        initial_company_name="Approval Company",
        initial_admin_username="manager",
        initial_admin_email="manager@example.com",
        initial_admin_password=SecretStr("Temporary123!"),
        initial_admin_employee_number="MGR-001",
        initial_admin_first_name="Mina",
        initial_admin_last_name="Manager",
        leave_attachment_dir=str(
            tmp_path / "leave_files"
        ),
        password_reset_outbox_dir=str(
            tmp_path / "outbox"
        ),
        password_reset_base_url="http://localhost:8501",
    )


def _factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )
    Base.metadata.create_all(engine)

    return sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )


def _employee_with_login(session, seed) -> tuple[Employee, User]:
    employee_user = User(
        company_id=seed["company"].id,
        role_id=seed["admin_user"].role_id,
        clearance=2,
        username="employee",
        email="employee@example.com",
        password_hash=seed["admin_user"].password_hash,
        is_active=True,
        must_change_password=False,
    )
    session.add(employee_user)
    session.flush()

    employee = Employee(
        company_id=seed["company"].id,
        user_id=employee_user.id,
        manager_id=seed["admin_employee"].id,
        employee_number="EMP-001",
        first_name="Ella",
        last_name="Employee",
        work_email="employee@example.com",
        employment_status="employed",
    )
    session.add(employee)
    session.commit()
    session.refresh(employee)

    return employee, employee_user


def _future_weekday() -> date:
    value = date.today() + timedelta(days=10)
    while value.weekday() >= 5:
        value += timedelta(days=1)
    return value


def test_submission_emails_manager_without_reserving_credits(
    tmp_path: Path,
) -> None:
    factory = _factory()
    sender = CapturingSender()

    with factory() as session:
        settings = _settings(tmp_path)
        seed = seed_initial_data(session, settings)
        seed["admin_employee"].work_email = (
            "manager@example.com"
        )
        employee, employee_user = _employee_with_login(
            session,
            seed,
        )
        service = LeaveService(
            session,
            settings=settings,
            email_sender=sender,
        )
        vacation = next(
            item
            for item in service.list_employee_balances(
                seed["company"].id,
                employee.id,
            )
            if item.leave_type.code == "VACATION"
        )
        start = _future_weekday()

        result = service.submit_leave_request(
            LeaveRequestInput(
                company_id=seed["company"].id,
                employee_id=employee.id,
                requested_by_user_id=employee_user.id,
                leave_type_id=vacation.leave_type_id,
                start_date=start,
                end_date=start,
                reason="Family commitment",
                handover_plan=(
                    "Daily report will be handled by the backup."
                ),
            )
        )

        refreshed = service.balance_repository.get_balance(
            company_id=seed["company"].id,
            employee_id=employee.id,
            leave_type_id=vacation.leave_type_id,
            year=start.year,
        )

        assert result.request.status == "pending_manager_approval"
        assert Decimal(
            refreshed.reserved_days
        ) == Decimal("0.00")
        assert Decimal(
            refreshed.remaining_days
        ) == Decimal("42.00")
        assert sender.messages
        assert (
            sender.messages[0].to_email
            == "manager@example.com"
        )
        assert "Work Handover Plan" in (
            sender.messages[0].text_body
        )
        assert "Review this request" in (
            sender.messages[0].text_body
        )


def test_manager_approval_reserves_matching_leave_type(
    tmp_path: Path,
) -> None:
    factory = _factory()
    sender = CapturingSender()

    with factory() as session:
        settings = _settings(tmp_path)
        seed = seed_initial_data(session, settings)
        seed["admin_employee"].work_email = (
            "manager@example.com"
        )
        employee, employee_user = _employee_with_login(
            session,
            seed,
        )
        service = LeaveService(
            session,
            settings=settings,
            email_sender=sender,
        )
        sick = next(
            item
            for item in service.list_employee_balances(
                seed["company"].id,
                employee.id,
            )
            if item.leave_type.code == "SICK"
        )
        start = _future_weekday()
        submitted = service.submit_leave_request(
            LeaveRequestInput(
                company_id=seed["company"].id,
                employee_id=employee.id,
                requested_by_user_id=employee_user.id,
                leave_type_id=sick.leave_type_id,
                start_date=start,
                end_date=start,
                reason="Medical appointment",
            )
        )

        approved = service.decide_leave_request(
            LeaveDecisionInput(
                company_id=seed["company"].id,
                request_id=submitted.request.id,
                manager_employee_id=seed["admin_employee"].id,
                manager_user_id=seed["admin_user"].id,
                decision="approve",
                manager_comment="Approved.",
            )
        )
        balance = service.balance_repository.get_balance(
            company_id=seed["company"].id,
            employee_id=employee.id,
            leave_type_id=sick.leave_type_id,
            year=start.year,
        )

        assert approved.status == "scheduled"
        assert approved.reservation_posted is True
        assert Decimal(
            balance.reserved_days
        ) == Decimal("1.00")
        assert Decimal(
            balance.remaining_days
        ) == Decimal("14.00")


def test_rejected_request_never_changes_credits(
    tmp_path: Path,
) -> None:
    factory = _factory()

    with factory() as session:
        settings = _settings(tmp_path)
        seed = seed_initial_data(session, settings)
        seed["admin_employee"].work_email = (
            "manager@example.com"
        )
        employee, employee_user = _employee_with_login(
            session,
            seed,
        )
        service = LeaveService(
            session,
            settings=settings,
            email_sender=CapturingSender(),
        )
        vacation = next(
            item
            for item in service.list_employee_balances(
                seed["company"].id,
                employee.id,
            )
            if item.leave_type.code == "VACATION"
        )
        start = _future_weekday()
        submitted = service.submit_leave_request(
            LeaveRequestInput(
                company_id=seed["company"].id,
                employee_id=employee.id,
                requested_by_user_id=employee_user.id,
                leave_type_id=vacation.leave_type_id,
                start_date=start,
                end_date=start,
                reason="Personal appointment",
            )
        )

        rejected = service.decide_leave_request(
            LeaveDecisionInput(
                company_id=seed["company"].id,
                request_id=submitted.request.id,
                manager_employee_id=seed["admin_employee"].id,
                manager_user_id=seed["admin_user"].id,
                decision="reject",
            )
        )
        balance = service.balance_repository.get_balance(
            company_id=seed["company"].id,
            employee_id=employee.id,
            leave_type_id=vacation.leave_type_id,
            year=start.year,
        )

        assert rejected.status == "rejected"
        assert Decimal(
            balance.reserved_days
        ) == Decimal("0.00")
        assert Decimal(
            balance.used_days
        ) == Decimal("0.00")
        assert Decimal(
            balance.remaining_days
        ) == Decimal("42.00")


def test_date_reconciliation_moves_reserved_to_used_once(
    tmp_path: Path,
) -> None:
    factory = _factory()

    with factory() as session:
        settings = _settings(tmp_path)
        seed = seed_initial_data(session, settings)
        seed["admin_employee"].work_email = (
            "manager@example.com"
        )
        employee, employee_user = _employee_with_login(
            session,
            seed,
        )
        service = LeaveService(
            session,
            settings=settings,
            email_sender=CapturingSender(),
        )
        vacation = next(
            item
            for item in service.list_employee_balances(
                seed["company"].id,
                employee.id,
            )
            if item.leave_type.code == "VACATION"
        )

        monday = date(2026, 8, 10)
        tuesday = date(2026, 8, 11)
        submitted = service.submit_leave_request(
            LeaveRequestInput(
                company_id=seed["company"].id,
                employee_id=employee.id,
                requested_by_user_id=employee_user.id,
                leave_type_id=vacation.leave_type_id,
                start_date=monday,
                end_date=tuesday,
                reason="Planned family leave",
                handover_plan="Two-day handover plan.",
            )
        )
        request = submitted.request
        request.status = "scheduled"
        request.approved_at = datetime.now(timezone.utc)
        request.reviewed_at = datetime.now(timezone.utc)
        request.reviewed_by_user_id = seed["admin_user"].id
        request.reservation_posted = True
        balance = service.balance_repository.get_balance(
            company_id=seed["company"].id,
            employee_id=employee.id,
            leave_type_id=vacation.leave_type_id,
            year=2026,
        )
        balance.reserved_days = Decimal("2.00")
        session.commit()

        changed = service.reconcile_approved_leave(
            company_id=seed["company"].id,
            through_date=monday,
        )
        first = service.balance_repository.get_balance(
            company_id=seed["company"].id,
            employee_id=employee.id,
            leave_type_id=vacation.leave_type_id,
            year=2026,
        )

        assert changed == 1
        assert Decimal(
            first.reserved_days
        ) == Decimal("1.00")
        assert Decimal(
            first.used_days
        ) == Decimal("1.00")

        service.reconcile_approved_leave(
            company_id=seed["company"].id,
            through_date=monday,
        )
        same_day = service.balance_repository.get_balance(
            company_id=seed["company"].id,
            employee_id=employee.id,
            leave_type_id=vacation.leave_type_id,
            year=2026,
        )
        assert Decimal(
            same_day.used_days
        ) == Decimal("1.00")

        service.reconcile_approved_leave(
            company_id=seed["company"].id,
            through_date=tuesday,
        )
        completed = service.get_request(
            seed["company"].id,
            request.id,
        )
        final_balance = service.balance_repository.get_balance(
            company_id=seed["company"].id,
            employee_id=employee.id,
            leave_type_id=vacation.leave_type_id,
            year=2026,
        )

        assert Decimal(
            final_balance.reserved_days
        ) == Decimal("0.00")
        assert Decimal(
            final_balance.used_days
        ) == Decimal("2.00")
        assert completed.status == "completed"


def test_required_handover_plan_accepts_text_or_file(
    tmp_path: Path,
) -> None:
    factory = _factory()

    with factory() as session:
        settings = _settings(tmp_path)
        seed = seed_initial_data(session, settings)
        seed["admin_employee"].work_email = (
            "manager@example.com"
        )
        employee, employee_user = _employee_with_login(
            session,
            seed,
        )
        service = LeaveService(
            session,
            settings=settings,
            email_sender=CapturingSender(),
        )
        vacation = next(
            item
            for item in service.list_employee_balances(
                seed["company"].id,
                employee.id,
            )
            if item.leave_type.code == "VACATION"
        )
        vacation.leave_type.handover_plan_requirement = (
            "required"
        )
        session.commit()
        start = _future_weekday()

        try:
            service.submit_leave_request(
                LeaveRequestInput(
                    company_id=seed["company"].id,
                    employee_id=employee.id,
                    requested_by_user_id=employee_user.id,
                    leave_type_id=vacation.leave_type_id,
                    start_date=start,
                    end_date=start,
                    reason="Planned leave request",
                )
            )
        except ValueError as error:
            assert "requires a work handover plan" in str(error)
        else:
            raise AssertionError(
                "Required handover plan was not enforced."
            )


def test_employee_ui_contains_full_discussed_flow() -> None:
    source = (
        PROJECT_ROOT
        / "ui/pages/user/leave_management_page.py"
    ).read_text(encoding="utf-8")

    assert '"File Leave Request"' in source
    assert '"Work Handover Plan / Countermeasure"' in source
    assert '"Optional Handover Plan File"' in source
    assert '"Pending Approvals"' in source
    assert '"Reviewed Requests"' in source
    assert '"Approve Leave Request"' in source
    assert '"Reject Leave Request"' in source
    assert '"To"' in source
    assert '"CC"' in source


def test_submission_does_not_reserve_before_approval() -> None:
    source = (
        PROJECT_ROOT
        / "services/leave_service.py"
    ).read_text(encoding="utf-8")

    submit = source.split(
        "def submit_leave_request(",
        1,
    )[1].split(
        "def is_manager(",
        1,
    )[0]

    assert 'status="pending_manager_approval"' in submit
    assert "balance.reserved_days =" not in submit
    assert "request_reserved" not in submit


def test_app_and_script_both_run_reconciliation() -> None:
    app_source = (
        PROJECT_ROOT / "app.py"
    ).read_text(encoding="utf-8")
    script_source = (
        PROJECT_ROOT
        / "scripts/reconcile_leave_credits.py"
    ).read_text(encoding="utf-8")

    assert "_reconcile_leave_credits(" in app_source
    assert "reconcile_approved_leave(" in app_source
    assert "reconcile_approved_leave(" in script_source
