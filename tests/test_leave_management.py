"""End-to-end service tests for leave credits and manager-routed requests."""

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
from repositories.employee_repository import EmployeeRepository
from schemas.leave_schema import LeaveCreditAdjustmentInput, LeaveRequestInput
from scripts.create_initial_data import seed_initial_data
from services.leave_service import LeaveService


class CapturingSender:
    def __init__(self) -> None:
        self.messages: list[OutboundEmail] = []
    def send(self, message: OutboundEmail) -> str:
        self.messages.append(message)
        return "captured"


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code="LEAVE",
        initial_company_name="Leave Company",
        initial_admin_username="admin",
        initial_admin_email="admin.leave@example.com",
        initial_admin_password=SecretStr("Temporary123!"),
        initial_admin_employee_number="ADMIN-001",
        initial_admin_first_name="System",
        initial_admin_last_name="Administrator",
        leave_attachment_dir=str(tmp_path / "leave_files"),
        password_reset_outbox_dir=str(tmp_path / "outbox"),
    )


def _factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _employee_pair(session, seed):
    admin_employee = seed["admin_employee"]
    admin_employee.work_email = "manager@leave.test"
    employee = Employee(
        company_id=seed["company"].id,
        department_id=admin_employee.department_id,
        manager_id=admin_employee.id,
        employee_number="EMP-001",
        first_name="Juan",
        last_name="Dela Cruz",
        work_email="juan@leave.test",
        job_title="Staff",
        employment_status="employed",
    )
    session.add(employee)
    session.commit()
    session.refresh(employee)
    return admin_employee, employee


def test_default_types_and_balances_are_created(tmp_path: Path) -> None:
    factory = _factory()
    with factory() as session:
        seed = seed_initial_data(session, _settings(tmp_path))
        _, employee = _employee_pair(session, seed)
        service = LeaveService(session, settings=_settings(tmp_path), email_sender=CapturingSender())
        types = service.list_leave_types(seed["company"].id)
        balances = service.list_employee_balances(seed["company"].id, employee.id)
        assert {item.code for item in types} >= {"VACATION", "SICK", "EMERGENCY", "LWOP"}
        assert {item.leave_type.code for item in balances} >= {"VACATION", "SICK"}


def test_adjustment_updates_remaining_and_history(tmp_path: Path) -> None:
    factory = _factory()
    with factory() as session:
        seed = seed_initial_data(session, _settings(tmp_path))
        _, employee = _employee_pair(session, seed)
        service = LeaveService(session, settings=_settings(tmp_path), email_sender=CapturingSender())
        balance = next(item for item in service.list_employee_balances(seed["company"].id, employee.id) if item.leave_type.code == "VACATION")
        updated = service.adjust_credit(
            LeaveCreditAdjustmentInput(
                company_id=seed["company"].id,
                employee_id=employee.id,
                leave_type_id=balance.leave_type_id,
                year=date.today().year,
                adjustment_days=Decimal("2.00"),
                reason="HR adjustment",
                created_by_user_id=seed["admin_user"].id,
            )
        )
        assert Decimal(updated.remaining_days) == Decimal("44.00")
        history = service.list_credit_history(seed["company"].id, employee.id)
        assert any(item.transaction_type == "manual_adjustment" for item in history)


def test_request_is_recorded_reserved_and_emailed(tmp_path: Path) -> None:
    factory = _factory()
    sender = CapturingSender()
    with factory() as session:
        settings = _settings(tmp_path)
        seed = seed_initial_data(session, settings)
        _, employee = _employee_pair(session, seed)
        # Reuse the test login identity for the requesting employee.
        # The manager remains reachable by work email.
        seed["admin_employee"].user_id = None
        employee.user_id = seed["admin_user"].id
        session.commit()
        service = LeaveService(session, settings=settings, email_sender=sender)
        vacation = next(item for item in service.list_employee_balances(seed["company"].id, employee.id) if item.leave_type.code == "VACATION")
        start = date.today() + timedelta(days=7)
        while start.weekday() >= 5:
            start += timedelta(days=1)
        result = service.submit_leave_request(
            LeaveRequestInput(
                company_id=seed["company"].id,
                employee_id=employee.id,
                requested_by_user_id=seed["admin_user"].id,
                leave_type_id=vacation.leave_type_id,
                start_date=start,
                end_date=start,
                reason="Family appointment",
            )
        )
        assert result.email_sent is True
        assert result.request.public_id.startswith("LRQ_")
        assert result.request.manager_email == "manager@leave.test"
        assert sender.messages[0].to_email == "manager@leave.test"
        assert "juan@leave.test" in sender.messages[0].cc_emails
        refreshed = service.balance_repository.get_balance(
            company_id=seed["company"].id,
            employee_id=employee.id,
            leave_type_id=vacation.leave_type_id,
            year=start.year,
        )
        # Submission does not reserve or deduct credits.
        assert Decimal(refreshed.reserved_days) == Decimal("0.00")
        assert result.request.status == "pending_manager_approval"
        assert service.notification_service.unread_count(
            company_id=seed["company"].id,
            user_id=seed["admin_user"].id,
        ) >= 1


def test_admin_ui_has_view_only_request_action() -> None:
    source = (Path(__file__).resolve().parents[1] / "ui/pages/admin/leave_management_page.py").read_text(encoding="utf-8")
    assert '"View Request Details"' in source
    assert "Approve" not in source
    assert "Reject" not in source
    assert "Cancel" not in source
