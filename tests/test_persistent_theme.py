"""Tests for persistent light/dark mode selection."""

from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from authentication.auth_service import AuthService
from config.settings import Settings
from database.base import Base
from scripts.create_initial_data import seed_initial_data
from services.persistent_session_service import (
    PersistentSessionService,
)


def _settings() -> Settings:
    """Return isolated seed settings."""

    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code="THEME",
        initial_company_name="Theme Test Company",
        initial_admin_username="admin",
        initial_admin_email="theme.admin@example.com",
        initial_admin_password=SecretStr(
            "Temporary123!"
        ),
        initial_admin_employee_number="THEME-001",
        initial_admin_first_name="Theme",
        initial_admin_last_name="Administrator",
    )


def _factory():
    """Return a fresh in-memory database."""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )
    Base.metadata.create_all(engine)

    return sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )


def _authenticated_user(session):
    """Seed and authenticate the administrator."""

    seed_initial_data(session, _settings())

    return AuthService(session).authenticate(
        company_code="THEME",
        login_identifier="admin",
        password="Temporary123!",
    )


def test_dark_theme_is_restored_after_refresh() -> None:
    """A dark selection should survive token restoration."""

    factory = _factory()

    with factory() as session:
        user = _authenticated_user(session)
        service = PersistentSessionService(session)

        created = service.create_session(
            current_user=user,
            lifetime_days=7,
            portal_mode="admin",
            current_page="Employees",
            theme="light",
        )

        service.update_theme(
            auth_session_id=created.auth_session_id,
            theme="dark",
        )

        restored = service.restore_session(
            raw_token=created.raw_token,
            idle_timeout_minutes=480,
        )

        assert restored is not None
        assert restored.current_page == "Employees"
        assert restored.theme == "dark"


def test_light_theme_is_restored_after_switching_back() -> None:
    """Switching back to light should overwrite dark preference."""

    factory = _factory()

    with factory() as session:
        user = _authenticated_user(session)
        service = PersistentSessionService(session)

        created = service.create_session(
            current_user=user,
            lifetime_days=7,
            theme="dark",
        )

        service.update_theme(
            auth_session_id=created.auth_session_id,
            theme="light",
        )

        restored = service.restore_session(
            raw_token=created.raw_token,
            idle_timeout_minutes=480,
        )

        assert restored is not None
        assert restored.theme == "light"


def test_theme_is_kept_separately_per_browser_session() -> None:
    """Different browser sessions may keep different themes."""

    factory = _factory()

    with factory() as session:
        user = _authenticated_user(session)
        service = PersistentSessionService(session)

        first = service.create_session(
            current_user=user,
            lifetime_days=7,
            theme="dark",
        )
        second = service.create_session(
            current_user=user,
            lifetime_days=7,
            theme="light",
        )

        first_restored = service.restore_session(
            raw_token=first.raw_token,
            idle_timeout_minutes=480,
        )
        second_restored = service.restore_session(
            raw_token=second.raw_token,
            idle_timeout_minutes=480,
        )

        assert first_restored is not None
        assert second_restored is not None
        assert first_restored.theme == "dark"
        assert second_restored.theme == "light"


def test_invalid_theme_falls_back_to_light() -> None:
    """Unsupported values should never enter restored UI state."""

    factory = _factory()

    with factory() as session:
        user = _authenticated_user(session)
        service = PersistentSessionService(session)

        created = service.create_session(
            current_user=user,
            lifetime_days=7,
            theme="unsupported",
        )

        restored = service.restore_session(
            raw_token=created.raw_token,
            idle_timeout_minutes=480,
        )

        assert restored is not None
        assert restored.theme == "light"
