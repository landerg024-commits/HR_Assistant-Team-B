"""Regression tests for detached Leave Management ORM relationships."""

from pathlib import Path

from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from config.settings import Settings
from database.base import Base
from models.department import Department
from models.employee import Employee
from scripts.create_initial_data import seed_initial_data
from services.leave_service import LeaveService


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _settings(tmp_path: Path) -> Settings:
    """Return isolated leave-test settings."""

    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code="LEAVEDETACH",
        initial_company_name="Leave Detached Company",
        initial_admin_username="admin",
        initial_admin_email="leave.detach@example.com",
        initial_admin_password=SecretStr("Temporary123!"),
        initial_admin_employee_number="ADMIN-001",
        initial_admin_first_name="System",
        initial_admin_last_name="Administrator",
        leave_attachment_dir=str(
            tmp_path / "leave_files"
        ),
        password_reset_outbox_dir=str(
            tmp_path / "outbox"
        ),
    )


def _factory():
    """Create an in-memory session factory."""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )
    Base.metadata.create_all(engine)

    return sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )


def _employee_with_department(
    session,
    seed,
) -> Employee:
    """Create an employed worker assigned to one department."""

    department = Department(
        company_id=seed["company"].id,
        name="Information Technology",
        code="IT",
        is_active=True,
    )
    session.add(department)
    session.flush()

    employee = Employee(
        company_id=seed["company"].id,
        department_id=department.id,
        manager_id=seed["admin_employee"].id,
        employee_number="EMP-DETACHED-001",
        first_name="Maria",
        last_name="Santos",
        work_email="maria.santos@example.com",
        job_title="Developer",
        employment_status="employed",
    )
    session.add(employee)
    session.commit()
    session.refresh(employee)

    return employee


def test_company_balances_keep_department_after_session_close(
    tmp_path: Path,
) -> None:
    """Admin Leave Credits may read employee.department when detached."""

    factory = _factory()

    with factory() as session:
        seed = seed_initial_data(
            session,
            _settings(tmp_path),
        )
        employee = _employee_with_department(
            session,
            seed,
        )
        balances = LeaveService(
            session,
            settings=_settings(tmp_path),
        ).list_company_balances(
            seed["company"].id
        )

        employee_balances = [
            item
            for item in balances
            if item.employee_id == employee.id
        ]

        assert employee_balances
        loaded_employee = employee_balances[0].employee

        # Verify the relationship was populated before detachment.
        employee_state = sqlalchemy_inspect(
            loaded_employee
        )
        assert "department" not in (
            employee_state.unloaded
        )

    # The Session is now closed, matching the Streamlit page flow.
    assert loaded_employee.department is not None
    assert (
        loaded_employee.department.name
        == "Information Technology"
    )
    assert loaded_employee.full_name == "Maria Santos"


def test_company_balance_relationships_are_loaded_before_detach(
    tmp_path: Path,
) -> None:
    """Leave type, employee, department, manager, and user are safe."""

    factory = _factory()

    with factory() as session:
        seed = seed_initial_data(
            session,
            _settings(tmp_path),
        )
        employee = _employee_with_department(
            session,
            seed,
        )
        balances = LeaveService(
            session,
            settings=_settings(tmp_path),
        ).list_company_balances(
            seed["company"].id
        )

        balance = next(
            item
            for item in balances
            if item.employee_id == employee.id
        )

        balance_state = sqlalchemy_inspect(balance)
        employee_state = sqlalchemy_inspect(
            balance.employee
        )

        assert "employee" not in balance_state.unloaded
        assert "leave_type" not in balance_state.unloaded
        assert "department" not in employee_state.unloaded
        assert "manager" not in employee_state.unloaded
        assert "user" not in employee_state.unloaded

    assert balance.leave_type.name
    assert balance.employee.department.name
    assert balance.employee.manager is not None


def test_repository_explicitly_eager_loads_department() -> None:
    """Protect the query from accidentally returning to lazy loading."""

    source = (
        PROJECT_ROOT
        / "repositories/leave_repository.py"
    ).read_text(encoding="utf-8")

    assert source.count(
        "LeaveBalance.employee"
    ) >= 9
    assert source.count(
        "Employee.department"
    ) >= 5
    assert (
        "joinedload(\n"
        "                    LeaveBalance.employee\n"
        "                ).joinedload(\n"
        "                    Employee.department"
        in source
    )
