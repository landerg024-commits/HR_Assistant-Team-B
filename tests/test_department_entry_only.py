"""Tests for department entry through Employee Add/Edit only."""

from pathlib import Path

from pydantic import SecretStr
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from config.settings import Settings
from database.base import Base
from models.department import Department
from schemas.admin_management_schema import EmployeeAccountCreate
from scripts.create_initial_data import seed_initial_data
from services.admin_management_service import AdminManagementService


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code="DEPTENTRY",
        initial_company_name="Department Entry Company",
        initial_admin_username="admin",
        initial_admin_email="admin.department@example.com",
        initial_admin_password=SecretStr("Temporary123!"),
        initial_admin_employee_number="ADMIN-001",
        initial_admin_first_name="System",
        initial_admin_last_name="Administrator",
    )


def test_departments_is_removed_from_sidebar() -> None:
    source = _read("ui/components/admin_sidebar.py")
    navigation = source.split(
        "ADMIN_NAVIGATION =",
        1,
    )[1].split(
        "def render_admin_sidebar",
        1,
    )[0]

    assert '"Employees"' in navigation
    assert '"Departments"' not in navigation


def test_old_departments_bookmark_redirects_to_employees() -> None:
    source = _read("ui/components/admin_sidebar.py")

    assert 'current_page == "Departments"' in source
    assert 'current_page="Employees"' in source


def test_admin_router_has_no_departments_route() -> None:
    source = _read("ui/layouts/admin_layout.py")

    assert "render_departments_page" not in source
    assert 'page == "Departments"' not in source


def test_department_is_entered_in_add_and_edit_employee() -> None:
    source = _read("ui/pages/admin/employees_page.py")

    assert source.count('department_name = st.text_input(') == 2
    assert "Matching is case-insensitive" in source
    assert "reused case-insensitively" in source
    assert "department records automatically" in source


def test_department_backend_remains_intact() -> None:
    assert '__tablename__ = "departments"' in _read(
        "models/department.py"
    )

    service_source = _read("services/admin_management_service.py")
    assert "DepartmentRepository" in service_source
    assert "def _resolve_department(" in service_source


def test_case_variants_reuse_one_department() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    with factory() as session:
        seed = seed_initial_data(session, _settings())
        service = AdminManagementService(session)

        rows = [
            (
                "EMP-101",
                "first.employee",
                "first.employee@example.com",
                "Information Technology",
            ),
            (
                "EMP-102",
                "second.employee",
                "second.employee@example.com",
                "information technology",
            ),
        ]

        for number, username, email, department_name in rows:
            service.create_employee_with_optional_account(
                EmployeeAccountCreate(
                    company_id=seed["company"].id,
                    employee_number=number,
                    first_name="Test",
                    last_name="Employee",
                    work_email=email,
                    department_name=department_name,
                    employment_status="employed",
                    create_login_account=True,
                    username=username,
                    login_email=email,
                    temporary_password="Temporary456!",
                    clearance=2,
                )
            )

        count = session.scalar(
            select(func.count(Department.id)).where(
                Department.company_id == seed["company"].id,
                func.lower(Department.name)
                == "information technology",
            )
        )

        assert count == 1
