"""Tests for the simplified default-account password-reset flow."""

from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from authentication.auth_service import AuthService
from config.settings import Settings
from database.base import Base
from scripts.create_initial_data import seed_initial_data


def _settings() -> Settings:
    """Return isolated initial-account settings."""

    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code="DEFAULT",
        initial_company_name="Sample Company",
        initial_admin_username="admin",
        initial_admin_email="default.admin@example.com",
        initial_admin_password=SecretStr("ChangeMe123!"),
        initial_admin_employee_number="ADMIN-001",
        initial_admin_first_name="System",
        initial_admin_last_name="Administrator",
    )


def _factory():
    """Return a fresh in-memory database session factory."""

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    return sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )


def test_new_default_admin_requires_password_change() -> None:
    """The seeded account must be blocked by the reset flag."""

    factory = _factory()

    with factory() as session:
        seed_initial_data(session, _settings())

        current_user = AuthService(session).authenticate(
            company_code="DEFAULT",
            login_identifier="admin",
            password="ChangeMe123!",
        )

        assert current_user.must_change_password is True


def test_password_change_clears_reset_flag() -> None:
    """A successful password replacement allows normal portal access."""

    factory = _factory()

    with factory() as session:
        seed_initial_data(session, _settings())
        service = AuthService(session)

        current_user = service.authenticate(
            company_code="DEFAULT",
            login_identifier="admin",
            password="ChangeMe123!",
        )

        updated_user = service.change_password(
            company_id=current_user.company_id,
            user_id=current_user.user_id,
            current_password="ChangeMe123!",
            new_password="NewSecure123!",
        )

        assert updated_user.must_change_password is False


def test_seed_rerun_does_not_force_another_reset() -> None:
    """The idempotent seed must preserve an already changed account."""

    factory = _factory()

    with factory() as session:
        settings = _settings()
        seed_initial_data(session, settings)
        service = AuthService(session)

        current_user = service.authenticate(
            company_code="DEFAULT",
            login_identifier="admin",
            password="ChangeMe123!",
        )

        service.change_password(
            company_id=current_user.company_id,
            user_id=current_user.user_id,
            current_password="ChangeMe123!",
            new_password="NewSecure123!",
        )

        seed_initial_data(session, settings)

        logged_in_again = service.authenticate(
            company_code="DEFAULT",
            login_identifier="admin",
            password="NewSecure123!",
        )

        assert logged_in_again.must_change_password is False
