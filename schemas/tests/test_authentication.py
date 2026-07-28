"""Authentication, password-change, and role-access tests."""

from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from authentication.access_control import AccessControl
from authentication.auth_service import (
    AuthenticationError,
    AuthService,
)
from config.settings import Settings
from database.base import Base
from repositories.role_repository import RoleRepository
from scripts.create_initial_data import seed_initial_data


def _settings() -> Settings:
    """Return valid isolated seed settings."""

    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code="AUTH",
        initial_company_name="Authentication Test Company",
        initial_admin_username="admin",
        initial_admin_email="admin.auth@example.com",
        initial_admin_password=SecretStr(
            "Temporary123!"
        ),
        initial_admin_employee_number="ADMIN-001",
        initial_admin_first_name="Test",
        initial_admin_last_name="Administrator",
    )


def _session_factory():
    """Create a fresh in-memory database factory."""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )
    Base.metadata.create_all(engine)

    return sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )


def test_admin_can_login_with_username() -> None:
    """Correct username credentials should authenticate."""

    factory = _session_factory()

    with factory() as session:
        seed_initial_data(session, _settings())

        current_user = AuthService(session).authenticate(
            company_code="AUTH",
            login_identifier="admin",
            password="Temporary123!",
        )

        assert current_user.username == "admin"
        assert current_user.role_name == "company_admin"
        assert current_user.must_change_password is True
        assert AccessControl.is_admin(current_user)


def test_admin_can_login_with_email() -> None:
    """The same account may authenticate using email."""

    factory = _session_factory()

    with factory() as session:
        seed_initial_data(session, _settings())

        current_user = AuthService(session).authenticate(
            company_code="AUTH",
            login_identifier="admin.auth@example.com",
            password="Temporary123!",
        )

        assert current_user.company_code == "AUTH"


def test_invalid_password_is_rejected() -> None:
    """Wrong passwords must fail authentication."""

    factory = _session_factory()

    with factory() as session:
        seed_initial_data(session, _settings())

        try:
            AuthService(session).authenticate(
                company_code="AUTH",
                login_identifier="admin",
                password="WrongPassword!",
            )
        except AuthenticationError:
            pass
        else:
            raise AssertionError(
                "Wrong password unexpectedly authenticated."
            )


def test_forced_password_change_clears_flag() -> None:
    """Replacing the temporary password should clear the lock flag."""

    factory = _session_factory()

    with factory() as session:
        seed_initial_data(session, _settings())
        service = AuthService(session)

        current_user = service.authenticate(
            company_code="AUTH",
            login_identifier="admin",
            password="Temporary123!",
        )

        updated_user = service.change_password(
            company_id=current_user.company_id,
            user_id=current_user.user_id,
            current_password="Temporary123!",
            new_password="Permanent456!",
        )

        assert updated_user.must_change_password is False

        reauthenticated = service.authenticate(
            company_code="AUTH",
            login_identifier="admin",
            password="Permanent456!",
        )

        assert reauthenticated.must_change_password is False


def test_employee_role_is_not_admin() -> None:
    """An employee role must not receive admin access."""

    factory = _session_factory()

    with factory() as session:
        seed_result = seed_initial_data(
            session,
            _settings(),
        )

        employee_role = RoleRepository(session).get_by_name(
            seed_result["company"].id,
            "employee",
        )
        assert employee_role is not None

        user = seed_result["admin_user"]
        user.role_id = employee_role.id
        session.commit()

        current_user = AuthService(session).authenticate(
            company_code="AUTH",
            login_identifier="admin",
            password="Temporary123!",
        )

        assert not AccessControl.is_admin(current_user)
        assert AccessControl.can_access_employee_portal(
            current_user
        )
