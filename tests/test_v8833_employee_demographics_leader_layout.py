"""Regression checks for employee demographics, leader, age, and N/A display."""

from datetime import date
from pathlib import Path

from models.employee import Employee


ROOT = Path(__file__).resolve().parents[1]


def test_full_name_omits_na_middle_name_and_suffix() -> None:
    employee = Employee(
        company_id=1,
        employee_number="EMP-001",
        first_name="Lander",
        middle_name="N/A",
        last_name="Garcia",
        suffix="N/A",
        employment_status="employed",
    )
    assert employee.full_name == "Lander Garcia"


def test_employee_age_is_calculated_from_birth_date() -> None:
    today = date.today()
    employee = Employee(
        company_id=1,
        employee_number="EMP-002",
        first_name="Sample",
        last_name="Employee",
        date_of_birth=date(today.year - 30, today.month, today.day),
        employment_status="employed",
    )
    assert employee.age == 30


def test_add_and_edit_forms_include_new_aligned_fields() -> None:
    source = (ROOT / "ui/pages/admin/employees_page.py").read_text(encoding="utf-8")
    assert source.count("department_column, manager_column, leader_column, position_column") >= 2
    assert source.count('"Leader"') >= 2
    assert source.count('"Gender"') >= 2
    assert source.count('"Civil Status"') >= 2
    assert source.count('"Date of Birth"') >= 2
    assert source.count('"Age"') >= 2


def test_employee_table_uses_na_and_new_columns() -> None:
    source = (ROOT / "ui/pages/admin/employees_page.py").read_text(encoding="utf-8")
    assert '"Leader": _display_value' in source
    assert '"Gender": _display_value' in source
    assert '"Civil Status": _display_value' in source
    assert '"Date of Birth":' in source
    assert '"Age": _display_value' in source
    assert 'return "N/A"' in source


def test_schema_upgrade_adds_new_employee_columns() -> None:
    source = (ROOT / "database/schema_upgrade.py").read_text(encoding="utf-8")
    for column in ("leader_id", "gender", "civil_status", "date_of_birth"):
        assert f'if "{column}" not in employee_columns' in source
