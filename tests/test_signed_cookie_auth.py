"""Tests for signed refresh-safe authentication cookies."""

from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from authentication.auth_service import AuthService
from authentication.signed_cookie_auth_service import (
    SignedCookieAuthenticationError,
    SignedCookieAuthService,
)
from config.settings import Settings
from database.base import Base
from scripts.create_initial_data import seed_initial_data


TEST_SECRET = "test-secret-value-long-enough-for-signing"


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code="COOKIE",
        initial_company_name="Cookie Company",
        initial_admin_username="admin",
        initial_admin_email="cookie.admin@example.com",
        initial_admin_password=SecretStr("ChangeMe123!"),
        initial_admin_employee_number="ADMIN-001",
        initial_admin_first_name="Cookie",
        initial_admin_last_name="Administrator",
        auth_cookie_secret=SecretStr(TEST_SECRET),
        auth_cookie_hours=12,
    )


def _factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    return sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )


def _authenticate(session):
    seed_initial_data(session, _settings())

    return AuthService(session).authenticate(
        company_code="COOKIE",
        login_identifier="admin",
        password="ChangeMe123!",
    )


def test_signed_cookie_restores_current_user() -> None:
    factory = _factory()

    with factory() as session:
        current_user = _authenticate(session)
        service = SignedCookieAuthService(
            session,
            secret_key=TEST_SECRET,
        )

        token = service.issue_token(current_user)
        restored = service.restore_user(token)

        assert restored.user_id == current_user.user_id
        assert restored.company_id == current_user.company_id
        assert restored.must_change_password is True


def test_tampered_cookie_is_rejected() -> None:
    factory = _factory()

    with factory() as session:
        current_user = _authenticate(session)
        service = SignedCookieAuthService(
            session,
            secret_key=TEST_SECRET,
        )

        token = service.issue_token(current_user)

        # Change the first character of the signature segment so the
        # decoded signature bytes are always different.
        token_parts = token.split(".")
        signature = token_parts[-1]
        token_parts[-1] = (
            ("x" if signature[0] != "x" else "y")
            + signature[1:]
        )
        tampered = ".".join(token_parts)

        try:
            service.restore_user(tampered)
        except SignedCookieAuthenticationError:
            pass
        else:
            raise AssertionError(
                "A modified authentication cookie was accepted."
            )


def test_password_change_invalidates_old_cookie() -> None:
    factory = _factory()

    with factory() as session:
        current_user = _authenticate(session)
        cookie_service = SignedCookieAuthService(
            session,
            secret_key=TEST_SECRET,
        )

        old_token = cookie_service.issue_token(current_user)

        updated_user = AuthService(session).change_password(
            company_id=current_user.company_id,
            user_id=current_user.user_id,
            current_password="ChangeMe123!",
            new_password="NewSecure123!",
        )

        try:
            cookie_service.restore_user(old_token)
        except SignedCookieAuthenticationError:
            pass
        else:
            raise AssertionError(
                "The old cookie remained valid after password change."
            )

        new_token = cookie_service.issue_token(updated_user)

        assert (
            cookie_service.restore_user(new_token).user_id
            == current_user.user_id
        )


def test_inactive_user_cookie_is_rejected() -> None:
    factory = _factory()

    with factory() as session:
        current_user = _authenticate(session)
        service = SignedCookieAuthService(
            session,
            secret_key=TEST_SECRET,
        )

        token = service.issue_token(current_user)

        user = service.user_repository.get_for_password_change(
            company_id=current_user.company_id,
            user_id=current_user.user_id,
        )
        assert user is not None

        user.is_active = False
        session.commit()

        try:
            service.restore_user(token)
        except SignedCookieAuthenticationError:
            pass
        else:
            raise AssertionError(
                "An inactive user's cookie was accepted."
            )
