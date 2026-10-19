"""Tests for protected permanent employee deletion."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from pydantic import SecretStr
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from config.settings import Settings
from database.base import Base
from models.department import Department
from models.employee import Employee
from models.employee_training import EmployeeTraining
from models.hr_policy import HRPolicy
from models.password_reset_token import PasswordResetToken
from models.user import User
from schemas.admin_management_schema import (
    EmployeeAccountCreate,
    EmployeeDeleteRequest,
    TrainingItemInput,
)
from scripts.create_initial_data import seed_initial_data
from services.admin_management_service import AdminManagementService


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code="DELETE",
        initial_company_name="Delete Company",
        initial_admin_username="admin",
        initial_admin_email="admin.delete@example.com",
        initial_admin_password=SecretStr("Temporary123!"),
        initial_admin_employee_number="ADMIN-001",
        initial_admin_first_name="System",
        initial_admin_last_name="Administrator",
    )


def _factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    return sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )


def _create_employee(
    service: AdminManagementService,
    company_id: int,
    *,
    number: str,
    username: str,
    email: str,
    manager_id: int | None = None,
):
    return service.create_employee_with_optional_account(
        EmployeeAccountCreate(
            company_id=company_id,
            employee_number=number,
            first_name="Delete",
            last_name="Candidate",
            work_email=email,
            department_name="Information Technology",
            manager_id=manager_id,
            employment_status="employed",
            trainings=[
                TrainingItemInput(
                    title="Orientation",
                    is_completed=True,
                )
            ],
            create_login_account=True,
            username=username,
            login_email=email,
            temporary_password="Temporary456!",
            clearance=2,
        )
    )


def _delete_request(employee):
    return EmployeeDeleteRequest(
        company_id=employee.company_id,
        employee_id=employee.id,
        permanent_delete_acknowledged=True,
    )


def test_delete_removes_related_records_but_keeps_department() -> None:
    factory = _factory()

    with factory() as session:
        seed = seed_initial_data(session, _settings())
        service = AdminManagementService(session)
        employee = _create_employee(
            service,
            seed["company"].id,
            number="EMP-DEL-001",
            username="delete.one",
            email="delete.one@example.com",
        )

        employee_id = employee.id
        user_id = employee.user.id
        department_id = employee.department.id

        now = datetime.now(timezone.utc)
        session.add(
            PasswordResetToken(
                company_id=seed["company"].id,
                user_id=user_id,
                token_hash="a" * 64,
                delivery_email=employee.work_email,
                requested_at=now,
                expires_at=now + timedelta(minutes=30),
                delivery_status="pending",
            )
        )
        session.commit()

        result = service.delete_employee_master_record(
            _delete_request(employee),
            current_user_id=seed["admin_user"].id,
        )

        assert result.employee_id == employee_id
        assert result.deleted_user_id == user_id
        assert session.get(Employee, employee_id) is None
        assert session.get(User, user_id) is None
        assert session.get(Department, department_id) is not None

        assert (
            session.scalar(
                select(func.count(EmployeeTraining.id)).where(
                    EmployeeTraining.employee_id == employee_id
                )
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count(PasswordResetToken.id)).where(
                    PasswordResetToken.user_id == user_id
                )
            )
            == 0
        )


def test_deleting_manager_clears_direct_report_manager() -> None:
    factory = _factory()

    with factory() as session:
        seed = seed_initial_data(session, _settings())
        service = AdminManagementService(session)

        manager = _create_employee(
            service,
            seed["company"].id,
            number="EMP-MGR-001",
            username="manager.one",
            email="manager.one@example.com",
        )
        report = _create_employee(
            service,
            seed["company"].id,
            number="EMP-REP-001",
            username="report.one",
            email="report.one@example.com",
            manager_id=manager.id,
        )

        result = service.delete_employee_master_record(
            _delete_request(manager),
            current_user_id=seed["admin_user"].id,
        )

        session.expire_all()
        remaining_report = session.get(Employee, report.id)

        assert result.cleared_manager_assignments == 1
        assert remaining_report is not None
        assert remaining_report.manager_id is None


def test_missing_acknowledgment_blocks_delete() -> None:
    factory = _factory()

    with factory() as session:
        seed = seed_initial_data(session, _settings())
        service = AdminManagementService(session)
        employee = _create_employee(
            service,
            seed["company"].id,
            number="EMP-DEL-002",
            username="delete.two",
            email="delete.two@example.com",
        )

        try:
            EmployeeDeleteRequest(
                company_id=employee.company_id,
                employee_id=employee.id,
                permanent_delete_acknowledged=False,
            )
        except Exception as error:
            assert "permanently deleted" in str(error)
        else:
            raise AssertionError(
                "Deletion acknowledgment was not required."
            )

        assert session.get(Employee, employee.id) is not None


def test_current_admin_cannot_delete_self() -> None:
    factory = _factory()

    with factory() as session:
        seed = seed_initial_data(session, _settings())
        service = AdminManagementService(session)

        try:
            service.delete_employee_master_record(
                EmployeeDeleteRequest(
                    company_id=seed["company"].id,
                    employee_id=seed["admin_employee"].id,
                    permanent_delete_acknowledged=True,
                ),
                current_user_id=seed["admin_user"].id,
            )
        except ValueError as error:
            assert "your own active" in str(error)
        else:
            raise AssertionError(
                "Current administrator self-deletion was allowed."
            )


def test_policy_history_blocks_delete() -> None:
    factory = _factory()

    with factory() as session:
        seed = seed_initial_data(session, _settings())
        service = AdminManagementService(session)
        employee = _create_employee(
            service,
            seed["company"].id,
            number="EMP-POL-001",
            username="policy.owner",
            email="policy.owner@example.com",
        )

        session.add(
            HRPolicy(
                company_id=seed["company"].id,
                created_by_user_id=employee.user.id,
                title="Retention Policy",
                category="Security",
                content="Keep policy author history.",
                version="1.0",
                status="published",
                effective_date=date.today(),
            )
        )
        session.commit()

        try:
            service.delete_employee_master_record(
                _delete_request(employee),
                current_user_id=seed["admin_user"].id,
            )
        except ValueError as error:
            assert "policy history" in str(error)
            assert "Resigned" in str(error)
        else:
            raise AssertionError(
                "Policy-history account deletion was allowed."
            )

        assert session.get(Employee, employee.id) is not None


def test_delete_ui_has_confirmation_and_warning() -> None:
    source = (
        PROJECT_ROOT
        / "ui/pages/admin/employees_page.py"
    ).read_text(encoding="utf-8")

    assert "Danger Zone — Delete Employee Record" in source
    assert "Type the exact Employee Number to confirm" not in source
    assert "Selected employee to delete" in source
    assert "Delete Employee Permanently" in source
    assert "disabled=not acknowledged" in source
    assert "linked login account" in source
    assert "EmployeeDeleteRequest" in source
