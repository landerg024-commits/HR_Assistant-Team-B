"""Persistent login-session service tests."""

from datetime import timedelta

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
    """Return isolated account settings."""

    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code="PERSIST",
        initial_company_name="Persistent Test Company",
        initial_admin_username="admin",
        initial_admin_email="persist.admin@example.com",
        initial_admin_password=SecretStr(
            "Temporary123!"
        ),
        initial_admin_employee_number="PERSIST-001",
        initial_admin_first_name="Persistent",
        initial_admin_last_name="Administrator",
    )


def _factory():
    """Return a new in-memory session factory."""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )
    Base.metadata.create_all(engine)

    return sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )


def _authenticated_user(session):
    """Seed and authenticate the initial administrator."""

    seed_initial_data(session, _settings())

    return AuthService(session).authenticate(
        company_code="PERSIST",
        login_identifier="admin",
        password="Temporary123!",
    )


def test_persistent_session_restores_user() -> None:
    """A valid raw token should restore the authenticated user."""

    factory = _factory()

    with factory() as session:
        current_user = _authenticated_user(session)
        service = PersistentSessionService(session)

        created = service.create_session(
            current_user=current_user,
            lifetime_days=7,
        )

        restored = service.restore_session(
            raw_token=created.raw_token,
            idle_timeout_minutes=480,
        )

        assert restored is not None
        assert restored.current_user.user_id == current_user.user_id
        assert restored.auth_session_id == created.auth_session_id


def test_database_stores_hash_not_raw_token() -> None:
    """The reusable raw cookie token must not be stored directly."""

    factory = _factory()

    with factory() as session:
        current_user = _authenticated_user(session)
        service = PersistentSessionService(session)

        created = service.create_session(
            current_user=current_user,
            lifetime_days=7,
        )

        stored = service.repository.get_by_id(
            created.auth_session_id
        )

        assert stored is not None
        assert stored.token_hash != created.raw_token
        assert len(stored.token_hash) == 64


def test_logout_revokes_token() -> None:
    """Revoked sessions must no longer restore authentication."""

    factory = _factory()

    with factory() as session:
        current_user = _authenticated_user(session)
        service = PersistentSessionService(session)

        created = service.create_session(
            current_user=current_user,
            lifetime_days=7,
        )

        service.revoke_token(created.raw_token)

        restored = service.restore_session(
            raw_token=created.raw_token,
            idle_timeout_minutes=480,
        )

        assert restored is None


def test_expired_session_cannot_restore() -> None:
    """Expired database sessions must be rejected."""

    factory = _factory()

    with factory() as session:
        current_user = _authenticated_user(session)
        service = PersistentSessionService(session)

        created = service.create_session(
            current_user=current_user,
            lifetime_days=7,
        )

        stored = service.repository.get_by_id(
            created.auth_session_id
        )
        assert stored is not None

        stored.expires_at = (
            service._utc_now() - timedelta(minutes=1)
        )
        session.commit()

        restored = service.restore_session(
            raw_token=created.raw_token,
            idle_timeout_minutes=480,
        )

        assert restored is None


def test_inactive_user_session_cannot_restore() -> None:
    """Account deactivation must invalidate persistent restoration."""

    factory = _factory()

    with factory() as session:
        current_user = _authenticated_user(session)
        service = PersistentSessionService(session)

        created = service.create_session(
            current_user=current_user,
            lifetime_days=7,
        )

        auth_session = service.repository.get_by_id(
            created.auth_session_id
        )
        assert auth_session is not None

        auth_session.user.is_active = False
        session.commit()

        restored = service.restore_session(
            raw_token=created.raw_token,
            idle_timeout_minutes=480,
        )

        assert restored is None


def test_active_session_id_is_touched_and_validated() -> None:
    """Authenticated reruns should update activity and remain valid."""

    factory = _factory()

    with factory() as session:
        current_user = _authenticated_user(session)
        service = PersistentSessionService(session)

        created = service.create_session(
            current_user=current_user,
            lifetime_days=7,
        )

        stored = service.repository.get_by_id(
            created.auth_session_id
        )
        assert stored is not None

        original_activity = stored.last_activity_at

        assert service.validate_session_id(
            auth_session_id=created.auth_session_id,
            idle_timeout_minutes=480,
        )

        session.refresh(stored)
        assert stored.last_activity_at >= original_activity
