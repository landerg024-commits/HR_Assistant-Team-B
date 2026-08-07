"""Regression tests for manual SL/VL retained-limit enforcement."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from config.settings import Settings
from database.base import Base
from models.employee import Employee
from models.leave_credit_transaction import LeaveCreditTransaction
from schemas.leave_schema import LeaveCreditBalanceSetInput
from scripts.create_initial_data import seed_initial_data
from services.leave_service import LeaveService


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code="V8857",
        initial_company_name="Manual Conversion Company",
        initial_admin_username="admin",
        initial_admin_email="admin@example.com",
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
        employee_number="EMP-V8857",
        first_name="Manual",
        last_name="Conversion",
        employment_status="employed",
        hire_date=date(2019, 8, 5),
    )
    session.add(employee)
    session.commit()
    session.refresh(employee)
    return employee


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


def test_manual_vacation_48_retains_45_and_converts_3(tmp_path: Path) -> None:
    factory = _factory()
    with factory() as session:
        settings = _settings(tmp_path)
        seed = seed_initial_data(session, settings)
        employee = _employee(session, seed)
        service = LeaveService(session, settings=settings)
        vacation = _balance(
            service,
            seed["company"].id,
            employee.id,
            "VACATION",
        )

        result = service.set_credit_balance(
            LeaveCreditBalanceSetInput(
                company_id=seed["company"].id,
                employee_id=employee.id,
                leave_type_id=vacation.leave_type_id,
                year=date.today().year,
                new_remaining_days=Decimal("48.00"),
                reason="Manual leave credit update",
                created_by_user_id=seed["admin_user"].id,
            )
        )

        assert result.requested_remaining == Decimal("48.00")
        assert result.new_remaining == Decimal("45.00")
        assert result.converted_to_cash == Decimal("3.00")
        assert Decimal(result.balance.available_credits) == Decimal("45.00")
        assert Decimal(result.balance.converted_to_cash_days) == Decimal("3.00")

        conversion = session.scalar(
            select(LeaveCreditTransaction).where(
                LeaveCreditTransaction.leave_balance_id == vacation.id,
                LeaveCreditTransaction.transaction_type
                == "cash_conversion_limit_enforcement",
            )
        )
        assert conversion is not None
        assert Decimal(conversion.amount_days) == Decimal("-3.00")


def test_manual_sick_20_retains_15_and_converts_5(tmp_path: Path) -> None:
    factory = _factory()
    with factory() as session:
        settings = _settings(tmp_path)
        seed = seed_initial_data(session, settings)
        employee = _employee(session, seed)
        service = LeaveService(session, settings=settings)
        sick = _balance(
            service,
            seed["company"].id,
            employee.id,
            "SICK",
        )

        result = service.set_credit_balance(
            LeaveCreditBalanceSetInput(
                company_id=seed["company"].id,
                employee_id=employee.id,
                leave_type_id=sick.leave_type_id,
                year=date.today().year,
                new_remaining_days=Decimal("20.00"),
                reason="Manual leave credit update",
                created_by_user_id=seed["admin_user"].id,
            )
        )

        assert result.new_remaining == Decimal("15.00")
        assert result.converted_to_cash == Decimal("5.00")
        assert Decimal(result.balance.available_credits) == Decimal("15.00")
        # The employee already received a 2-day January conversion because the
        # six-year service accrual is 17 SL days. The manual 5-day excess is
        # added to that immutable conversion history.
        assert Decimal(result.balance.converted_to_cash_days) == Decimal("7.00")


def test_existing_vacation_48_is_repaired_when_balances_load(tmp_path: Path) -> None:
    factory = _factory()
    with factory() as session:
        settings = _settings(tmp_path)
        seed = seed_initial_data(session, settings)
        employee = _employee(session, seed)
        service = LeaveService(session, settings=settings)
        vacation = _balance(
            service,
            seed["company"].id,
            employee.id,
            "VACATION",
        )

        # Simulate a v8.8.56 record saved before the retained-limit guard.
        vacation.adjustment_days += Decimal("31.00")
        service._sync_credit_table_columns(vacation)
        vacation.converted_to_cash_days = Decimal("0.00")
        session.commit()
        assert Decimal(vacation.available_credits) == Decimal("48.00")

        refreshed = _balance(
            service,
            seed["company"].id,
            employee.id,
            "VACATION",
        )
        session.commit()

        assert Decimal(refreshed.available_credits) == Decimal("45.00")
        assert Decimal(refreshed.converted_to_cash_days) == Decimal("3.00")

        first_count = len(
            session.scalars(
                select(LeaveCreditTransaction).where(
                    LeaveCreditTransaction.leave_balance_id == refreshed.id,
                    LeaveCreditTransaction.transaction_type
                    == "cash_conversion_limit_enforcement",
                )
            ).all()
        )
        _balance(
            service,
            seed["company"].id,
            employee.id,
            "VACATION",
        )
        session.commit()
        second_count = len(
            session.scalars(
                select(LeaveCreditTransaction).where(
                    LeaveCreditTransaction.leave_balance_id == refreshed.id,
                    LeaveCreditTransaction.transaction_type
                    == "cash_conversion_limit_enforcement",
                )
            ).all()
        )
        assert second_count == first_count


def test_admin_editor_explains_automatic_conversion() -> None:
    source = (
        PROJECT_ROOT / "ui/pages/admin/leave_management_page.py"
    ).read_text(encoding="utf-8")
    editor = source.split(
        "def _render_credit_balance_editor(", 1
    )[1].split("def _credit_history_entry(", 1)[0]

    assert "Retention limit" in editor
    assert "automatically moved to" in editor
    assert "result.converted_to_cash" in editor
    assert "days converted to cash" in editor
