"""End-to-end service tests for an employee-only account."""

from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from authentication.access_control import AccessControl
from authentication.auth_service import AuthService
from authentication.signed_cookie_auth_service import (
    SignedCookieAuthService,
)
from config.settings import Settings
from database.base import Base
from repositories.role_repository import RoleRepository
from schemas.admin_management_schema import EmployeeAccountCreate
from scripts.create_initial_data import seed_initial_data
from services.admin_management_service import (
    AdminManagementService,
)


TEST_COOKIE_SECRET = (
    "employee-only-test-cookie-secret-value"
)


def _settings() -> Settings:
    """Return isolated company settings."""

    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code="EMPONLY",
        initial_company_name="Employee Only Company",
        initial_admin_username="admin",
        initial_admin_email="admin.emponly@example.com",
        initial_admin_password=SecretStr("ChangeMe123!"),
        initial_admin_employee_number="ADMIN-001",
        initial_admin_first_name="System",
        initial_admin_last_name="Administrator",
        auth_cookie_secret=SecretStr(
            TEST_COOKIE_SECRET
        ),
        auth_cookie_hours=12,
    )


def _factory():
    """Return an isolated in-memory session factory."""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )
    Base.metadata.create_all(engine)

    return sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )


def _create_employee_account(session):
    """Seed the company and create one employee-role account."""

    seed = seed_initial_data(session, _settings())

    employee_role = RoleRepository(session).get_by_name(
        seed["company"].id,
        "employee",
    )
    assert employee_role is not None

    employee = AdminManagementService(
        session
    ).create_employee_with_optional_account(
        EmployeeAccountCreate(
            company_id=seed["company"].id,
            employee_number="EMP-001",
            first_name="Juan",
            last_name="Dela Cruz",
            work_email="juan.employee@example.com",
            job_title="Production Employee",
            create_login_account=True,
            role_id=employee_role.id,
            username="juan.employee",
            login_email="juan.login@example.com",
            temporary_password="Employee123!",
        )
    )

    assert employee.user is not None

    return seed, employee


def test_employee_login_has_employee_role_only() -> None:
    """Employee credentials must authenticate as employee."""

    factory = _factory()

    with factory() as session:
        seed, employee = _create_employee_account(session)

        current_user = AuthService(session).authenticate(
            company_code=seed["company"].code,
            login_identifier="juan.employee",
            password="Employee123!",
        )

        assert current_user.clearance == 2
        assert current_user.employee_id == employee.id
        assert current_user.employee_number == "EMP-001"
        assert current_user.must_change_password is True


def test_employee_has_no_administrator_permission() -> None:
    """Employee role must never pass administrator checks."""

    factory = _factory()

    with factory() as session:
        seed, _employee = _create_employee_account(session)

        current_user = AuthService(session).authenticate(
            company_code=seed["company"].code,
            login_identifier="juan.employee",
            password="Employee123!",
        )

        assert AccessControl.is_admin(current_user) is False
        assert (
            AccessControl.can_access_employee_portal(
                current_user
            )
            is True
        )

        try:
            AccessControl.require_admin(current_user)
        except PermissionError:
            pass
        else:
            raise AssertionError(
                "Employee account passed require_admin()."
            )


def test_employee_password_change_clears_reset_flag() -> None:
    """Temporary employee password must be replaced before portal use."""

    factory = _factory()

    with factory() as session:
        seed, _employee = _create_employee_account(session)
        service = AuthService(session)

        current_user = service.authenticate(
            company_code=seed["company"].code,
            login_identifier="juan.employee",
            password="Employee123!",
        )

        updated_user = service.change_password(
            company_id=current_user.company_id,
            user_id=current_user.user_id,
            current_password="Employee123!",
            new_password="EmployeeSecure123!",
        )

        assert updated_user.clearance == 2
        assert updated_user.must_change_password is False


def test_employee_signed_cookie_restores_employee_only() -> None:
    """Refresh cookie must restore the employee without elevating role."""

    factory = _factory()

    with factory() as session:
        seed, _employee = _create_employee_account(session)

        current_user = AuthService(session).authenticate(
            company_code=seed["company"].code,
            login_identifier="juan.employee",
            password="Employee123!",
        )

        cookie_service = SignedCookieAuthService(
            session,
            secret_key=TEST_COOKIE_SECRET,
        )

        token = cookie_service.issue_token(current_user)
        restored_user = cookie_service.restore_user(token)

        assert restored_user.clearance == 2
        assert AccessControl.is_admin(restored_user) is False
        assert (
            AccessControl.can_access_employee_portal(
                restored_user
            )
            is True
        )


def test_employee_and_admin_accounts_remain_separate() -> None:
    """Employee login must not reuse or inherit the admin account."""

    factory = _factory()

    with factory() as session:
        seed, employee = _create_employee_account(session)

        employee_user = AuthService(session).authenticate(
            company_code=seed["company"].code,
            login_identifier="juan.employee",
            password="Employee123!",
        )

        assert (
            employee_user.user_id
            != seed["admin_user"].id
        )
        assert (
            employee_user.employee_id
            != seed["admin_employee"].id
        )
        assert employee.user_id == employee_user.user_id
