"""Tests for revocable refresh-safe authentication sessions."""

from datetime import datetime, timedelta, timezone

from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from authentication.auth_service import AuthService
from authentication.persistent_auth_service import (
    PersistentAuthService,
    PersistentSessionError,
)
from config.settings import Settings
from database.base import Base
from models.auth_session import AuthSession
from scripts.create_initial_data import seed_initial_data


def _settings() -> Settings:
    """Create isolated authentication seed settings."""

    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code="PERSIST",
        initial_company_name="Persistent Session Company",
        initial_admin_username="admin",
        initial_admin_email="persistent.admin@example.com",
        initial_admin_password=SecretStr("Temporary123!"),
        initial_admin_employee_number="ADMIN-001",
        initial_admin_first_name="Persistent",
        initial_admin_last_name="Administrator",
        auth_session_hours=12,
    )


def _factory():
    """Return a fresh in-memory database session factory."""

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    return sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )


def _authenticated_user(session):
    """Seed and authenticate the initial company administrator."""

    seed_initial_data(session, _settings())

    return AuthService(session).authenticate(
        company_code="PERSIST",
        login_identifier="admin",
        password="Temporary123!",
    )


def test_issued_token_restores_authenticated_user() -> None:
    """A valid opaque token should restore safe user data."""

    factory = _factory()

    with factory() as session:
        current_user = _authenticated_user(session)
        service = PersistentAuthService(
            session,
            session_hours=12,
        )

        raw_token = service.issue_session(current_user)
        restored = service.restore_session(raw_token)

        assert restored.user_id == current_user.user_id
        assert restored.company_id == current_user.company_id
        assert restored.role_name == "company_admin"


def test_database_stores_only_token_hash() -> None:
    """The raw browser token must never be stored in the database."""

    factory = _factory()

    with factory() as session:
        current_user = _authenticated_user(session)
        service = PersistentAuthService(
            session,
            session_hours=12,
        )

        raw_token = service.issue_session(current_user)
        record = session.scalar(select(AuthSession))

        assert record is not None
        assert record.token_hash != raw_token
        assert len(record.token_hash) == 64
        assert (
            record.token_hash
            == service.hash_token(raw_token)
        )


def test_revoked_token_is_rejected() -> None:
    """Logout revocation must prevent refresh restoration."""

    factory = _factory()

    with factory() as session:
        current_user = _authenticated_user(session)
        service = PersistentAuthService(
            session,
            session_hours=12,
        )

        raw_token = service.issue_session(current_user)
        service.revoke_session(raw_token)

        try:
            service.restore_session(raw_token)
        except PersistentSessionError:
            pass
        else:
            raise AssertionError(
                "A revoked session token was accepted."
            )


def test_expired_token_is_rejected() -> None:
    """Expired sessions must not restore authentication."""

    factory = _factory()

    with factory() as session:
        current_user = _authenticated_user(session)
        service = PersistentAuthService(
            session,
            session_hours=12,
        )

        raw_token = service.issue_session(current_user)
        record = session.scalar(select(AuthSession))
        assert record is not None

        record.expires_at = (
            datetime.now(timezone.utc)
            - timedelta(minutes=1)
        )
        session.commit()

        try:
            service.restore_session(raw_token)
        except PersistentSessionError:
            pass
        else:
            raise AssertionError(
                "An expired session token was accepted."
            )


def test_inactive_user_session_is_rejected() -> None:
    """Deactivating a user must invalidate its browser session."""

    factory = _factory()

    with factory() as session:
        current_user = _authenticated_user(session)
        service = PersistentAuthService(
            session,
            session_hours=12,
        )

        raw_token = service.issue_session(current_user)

        user = service.user_repository.get_for_password_change(
            company_id=current_user.company_id,
            user_id=current_user.user_id,
        )
        assert user is not None

        user.is_active = False
        session.commit()

        try:
            service.restore_session(raw_token)
        except PersistentSessionError:
            pass
        else:
            raise AssertionError(
                "An inactive user's session was accepted."
            )


def test_rotation_revokes_old_token() -> None:
    """Password-style rotation should replace all old sessions."""

    factory = _factory()

    with factory() as session:
        current_user = _authenticated_user(session)
        service = PersistentAuthService(
            session,
            session_hours=12,
        )

        old_token = service.issue_session(current_user)
        new_token = service.rotate_user_sessions(current_user)

        assert new_token != old_token
        assert service.restore_session(new_token).user_id == (
            current_user.user_id
        )

        try:
            service.restore_session(old_token)
        except PersistentSessionError:
            pass
        else:
            raise AssertionError(
                "The pre-rotation token remained valid."
            )
