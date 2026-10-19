"""v8.8.63 leave-credit accounting column separation tests."""

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
from schemas.leave_schema import LeaveCreditBalanceSetInput
from scripts.create_initial_data import seed_initial_data
from services.leave_service import LeaveService


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code="V8863",
        initial_company_name="Ledger Columns Company",
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
        employee_number="EMP-V8863",
        first_name="Ledger",
        last_name="Employee",
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


def test_manual_exact_balance_preserves_credit_and_uses_adjustment(
    tmp_path: Path,
) -> None:
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

        assert Decimal(vacation.credit_days) == Decimal("17.00")
        assert Decimal(vacation.adjustment_days) == Decimal("0.00")

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

        assert Decimal(result.balance.credit_days) == Decimal("17.00")
        assert Decimal(result.balance.adjustment_days) == Decimal("31.00")
        assert Decimal(result.balance.converted_to_cash_days) == Decimal("3.00")
        assert Decimal(result.balance.available_credits) == Decimal("45.00")


def test_sync_reclassifies_old_combined_credit_without_changing_total(
    tmp_path: Path,
) -> None:
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

        sick.adjustment_days = Decimal("5.50")
        sick.credit_days = Decimal("22.50")  # v8.8.62 combined display
        sick.converted_to_cash_days = Decimal("7.50")
        session.commit()

        refreshed = _balance(
            service,
            seed["company"].id,
            employee.id,
            "SICK",
        )
        session.commit()

        assert Decimal(refreshed.credit_days) == Decimal("17.00")
        assert Decimal(refreshed.adjustment_days) == Decimal("5.50")
        assert Decimal(refreshed.converted_to_cash_days) == Decimal("7.50")
        assert Decimal(refreshed.available_credits) == Decimal("15.00")


def test_tables_show_simplified_accounting_columns() -> None:
    for relative_path in (
        "ui/pages/admin/leave_management_page.py",
        "ui/pages/user/leave_management_page.py",
    ):
        source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        for header in (
            "Beginning Credit",
            "Credit",
            "Used",
            "Available Credits",
            "Converted to Cash",
            "Last Updated",
        ):
            assert f'"{header}"' in source
        assert '"Adjustment":' not in source


def test_event_grant_is_credit_not_adjustment(tmp_path: Path) -> None:
    source = (
        PROJECT_ROOT / "services/leave_service.py"
    ).read_text(encoding="utf-8")
    grant = source.split(
        "def _grant_event_leave_entitlement(", 1
    )[1].split("def emergency_allowance_summary(", 1)[0]

    assert "balance.allocated_days" in grant
    assert "balance.adjustment_days" not in grant
