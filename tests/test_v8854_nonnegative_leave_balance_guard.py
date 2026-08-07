"""Regression tests for the strict non-negative leave balance guard."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from config.settings import Settings
from database.base import Base
from models.employee import Employee
from scripts.create_initial_data import seed_initial_data
from services.leave_service import LeaveService


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code="NONNEG",
        initial_company_name="Nonnegative Leave Company",
        initial_admin_username="admin",
        initial_admin_email="admin.nonnegative@example.com",
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


def _employee(session, seed) -> Employee:
    employee = Employee(
        company_id=seed["company"].id,
        manager_id=seed["admin_employee"].id,
        employee_number="EMP-NONNEG-001",
        first_name="Maya",
        last_name="Reyes",
        work_email="maya@example.com",
        employment_status="employed",
        hire_date=date(2020, 1, 1),
    )
    session.add(employee)
    session.commit()
    session.refresh(employee)
    return employee


def test_public_available_credits_never_returns_negative(tmp_path: Path) -> None:
    factory = _factory()
    with factory() as session:
        settings = _settings(tmp_path)
        seed = seed_initial_data(session, settings)
        employee = _employee(session, seed)
        service = LeaveService(session, settings=settings)
        vacation = next(
            item
            for item in service.list_employee_balances(
                seed["company"].id, employee.id
            )
            if item.leave_type.code == "VACATION"
        )

        vacation.adjustment_days = Decimal("-49.00")
        vacation.credit_days = (
            Decimal(vacation.allocated_days)
            + Decimal(vacation.adjustment_days)
        )
        session.commit()

        assert Decimal(vacation.calculated_available_credits) < 0
        assert Decimal(vacation.available_credits) == Decimal("0.00")
        assert Decimal(vacation.remaining_days) == Decimal("0.00")


def test_portal_balance_loading_repairs_legacy_negative_to_zero(
    tmp_path: Path,
) -> None:
    factory = _factory()
    with factory() as session:
        settings = _settings(tmp_path)
        seed = seed_initial_data(session, settings)
        employee = _employee(session, seed)
        service = LeaveService(session, settings=settings)
        vacation = next(
            item
            for item in service.list_employee_balances(
                seed["company"].id, employee.id
            )
            if item.leave_type.code == "VACATION"
        )

        vacation.used_days = Decimal("49.00")
        session.commit()
        assert Decimal(vacation.calculated_available_credits) < 0

        refreshed = next(
            item
            for item in service.list_employee_balances(
                seed["company"].id, employee.id
            )
            if item.leave_type.code == "VACATION"
        )

        assert Decimal(refreshed.calculated_available_credits) == Decimal("0.00")
        assert Decimal(refreshed.available_credits) == Decimal("0.00")
        assert Decimal(refreshed.used_days) == Decimal("49.00")

        repair_entries = [
            item
            for item in service.list_credit_history(
                seed["company"].id, employee.id
            )
            if item.transaction_type == "negative_balance_repair"
        ]
        assert len(repair_entries) == 1
        assert Decimal(repair_entries[0].amount_days) > 0

        service.list_employee_balances(seed["company"].id, employee.id)
        repair_entries = [
            item
            for item in service.list_credit_history(
                seed["company"].id, employee.id
            )
            if item.transaction_type == "negative_balance_repair"
        ]
        assert len(repair_entries) == 1


def test_service_contains_write_guards_and_lwop_instruction() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "services/leave_service.py"
    ).read_text(encoding="utf-8")

    assert "def _repair_negative_balance(" in source
    assert "def _validate_nonnegative_balance(" in source
    assert 'transaction_type="negative_balance_repair"' in source
    assert "use Leave Without Pay" in source
    assert "self._validate_nonnegative_balance(reserved_balance)" in source
