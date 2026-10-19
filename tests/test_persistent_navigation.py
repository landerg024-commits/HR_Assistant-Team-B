"""Tests for exact portal/page restoration after refresh."""

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
    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code="NAVTEST",
        initial_company_name="Navigation Test Company",
        initial_admin_username="admin",
        initial_admin_email="nav.admin@example.com",
        initial_admin_password=SecretStr("Temporary123!"),
        initial_admin_employee_number="NAV-001",
        initial_admin_first_name="Navigation",
        initial_admin_last_name="Administrator",
    )


def _factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _authenticated_user(session):
    seed_initial_data(session, _settings())
    return AuthService(session).authenticate(
        company_code="NAVTEST",
        login_identifier="admin",
        password="Temporary123!",
    )


def test_refresh_restores_exact_admin_page() -> None:
    factory = _factory()
    with factory() as session:
        user = _authenticated_user(session)
        service = PersistentSessionService(session)
        created = service.create_session(
            current_user=user,
            lifetime_days=7,
            portal_mode="admin",
            current_page="Admin Dashboard",
        )
        service.update_navigation(
            auth_session_id=created.auth_session_id,
            portal_mode="admin",
            current_page="Departments",
        )
        restored = service.restore_session(
            raw_token=created.raw_token,
            idle_timeout_minutes=480,
        )
        assert restored is not None
        assert restored.portal_mode == "admin"
        assert restored.current_page == "Departments"


def test_employee_portal_page_is_restored() -> None:
    factory = _factory()
    with factory() as session:
        user = _authenticated_user(session)
        service = PersistentSessionService(session)
        created = service.create_session(
            current_user=user,
            lifetime_days=7,
            portal_mode="employee",
            current_page="Company Policies",
        )
        restored = service.restore_session(
            raw_token=created.raw_token,
            idle_timeout_minutes=480,
        )
        assert restored is not None
        assert restored.portal_mode == "employee"
        assert restored.current_page == "Company Policies"


def test_each_browser_session_keeps_its_own_page() -> None:
    factory = _factory()
    with factory() as session:
        user = _authenticated_user(session)
        service = PersistentSessionService(session)
        first = service.create_session(
            current_user=user,
            lifetime_days=7,
            portal_mode="admin",
            current_page="Users",
        )
        second = service.create_session(
            current_user=user,
            lifetime_days=7,
            portal_mode="admin",
            current_page="Roles",
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
        assert first_restored.current_page == "Users"
        assert second_restored.current_page == "Roles"
