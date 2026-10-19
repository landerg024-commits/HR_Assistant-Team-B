"""Phase 1 tests for the seven-row leave credit ledger."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from pydantic import SecretStr
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from config.settings import Settings
from database.base import Base
from database.schema_upgrade import upgrade_existing_schema
from models.employee import Employee
from scripts.create_initial_data import seed_initial_data
from services.leave_service import (
    LEAVE_CREDIT_TABLE_CODES,
    LeaveService,
)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code="PHASE1",
        initial_company_name="Phase 1 Company",
        initial_admin_username="admin",
        initial_admin_email="admin@example.com",
        initial_admin_password=SecretStr("Temporary123!"),
        initial_admin_employee_number="ADMIN-001",
        initial_admin_first_name="System",
        initial_admin_last_name="Administrator",
        leave_attachment_dir=str(tmp_path / "leave_files"),
        password_reset_outbox_dir=str(tmp_path / "outbox"),
    )


def test_seven_leave_rows_and_new_columns_are_created(tmp_path: Path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with factory() as session:
        settings = _settings(tmp_path)
        seed = seed_initial_data(session, settings)
        employee = Employee(
            company_id=seed["company"].id,
            manager_id=seed["admin_employee"].id,
            employee_number="EMP-001",
            first_name="Ella",
            last_name="Employee",
            employment_status="employed",
            hire_date=date.today(),
        )
        session.add(employee)
        session.commit()

        service = LeaveService(session, settings=settings)
        balances = service.list_employee_balances(
            seed["company"].id, employee.id
        )
        table_balances = service.credit_table_balances(balances)

        assert tuple(
            item.leave_type.code for item in table_balances
        ) == LEAVE_CREDIT_TABLE_CODES
        assert len(table_balances) == 7
        assert all(
            Decimal(item.converted_to_cash_days) == Decimal("0.00")
            for item in table_balances
        )
        assert all(
            Decimal(item.credit_days) == Decimal(item.allocated_days)
            for item in table_balances
        )

    column_names = {
        column["name"]
        for column in inspect(engine).get_columns("leave_balances")
    }
    assert {
        "beginning_credit_days",
        "credit_days",
        "converted_to_cash_days",
    } <= column_names


def test_legacy_balance_is_preserved_and_backfilled() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE leave_balances ("
                "id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL, "
                "employee_id INTEGER NOT NULL, leave_type_id INTEGER NOT NULL, "
                "year INTEGER NOT NULL, allocated_days NUMERIC(8,2) NOT NULL, "
                "carry_over_days NUMERIC(8,2) NOT NULL, "
                "adjustment_days NUMERIC(8,2) NOT NULL, "
                "used_days NUMERIC(8,2) NOT NULL, "
                "reserved_days NUMERIC(8,2) NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO leave_balances VALUES "
                "(1, 1, 1, 1, 2026, 15, 4, 2, 3, 1)"
            )
        )

    upgrade_existing_schema(engine)

    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT allocated_days, carry_over_days, adjustment_days, "
                "used_days, reserved_days, beginning_credit_days, "
                "credit_days, converted_to_cash_days "
                "FROM leave_balances WHERE id = 1"
            )
        ).mappings().one()

    assert Decimal(row["allocated_days"]) == Decimal("15")
    assert Decimal(row["carry_over_days"]) == Decimal("4")
    assert Decimal(row["adjustment_days"]) == Decimal("2")
    assert Decimal(row["used_days"]) == Decimal("3")
    assert Decimal(row["reserved_days"]) == Decimal("1")
    assert Decimal(row["beginning_credit_days"]) == Decimal("4")
    assert Decimal(row["credit_days"]) == Decimal("15")
    assert Decimal(row["converted_to_cash_days"]) == Decimal("0")


def test_leave_tables_use_required_headers_and_fixed_height() -> None:
    project = Path(__file__).resolve().parents[1]
    admin_source = (
        project / "ui/pages/admin/leave_management_page.py"
    ).read_text(encoding="utf-8")
    employee_source = (
        project / "ui/pages/user/leave_management_page.py"
    ).read_text(encoding="utf-8")

    for source in (admin_source, employee_source):
        assert '"Beginning Credit"' in source
        assert '"Credit"' in source
        assert '"Adjustment":' not in source
        assert '"Used"' in source
        assert '"Available Credits"' in source
        assert '"Converted to Cash"' in source
        assert '"Last Updated"' in source
        assert "max_height=330" in source
