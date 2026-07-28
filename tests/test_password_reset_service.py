"""End-to-end tests for secure forgot-password behavior."""

from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from authentication.auth_service import (
    AuthenticationError,
    AuthService,
)
from authentication.password_reset_service import (
    GENERIC_RESET_REQUEST_MESSAGE,
    PasswordResetError,
    PasswordResetService,
)
from authentication.signed_cookie_auth_service import (
    SignedCookieAuthenticationError,
    SignedCookieAuthService,
)
from config.settings import Settings
from database.base import Base
from integrations.email.email_sender import (
    OutboundEmail,
)
from models.password_reset_token import PasswordResetToken
from scripts.create_initial_data import seed_initial_data


class CapturingEmailSender:
    """In-memory email adapter used by tests."""

    def __init__(self) -> None:
        self.messages: list[OutboundEmail] = []

    def send(self, message: OutboundEmail) -> str:
        self.messages.append(message)
        return "captured"


def _settings(
    code: str,
    email: str,
) -> Settings:
    """Return isolated reset settings."""

    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code=code,
        initial_company_name=f"{code} Company",
        initial_admin_username=f"{code.lower()}admin",
        initial_admin_email=email,
        initial_admin_password=SecretStr(
            "OriginalPassword123!"
        ),
        initial_admin_employee_number=f"{code}-001",
        initial_admin_first_name="System",
        initial_admin_last_name="Administrator",
        password_reset_base_url="http://localhost:8501",
        password_reset_token_minutes=30,
        password_reset_request_cooldown_seconds=60,
        email_delivery_mode="local",
    )


def _factory():
    """Create an isolated database."""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )
    Base.metadata.create_all(engine)

    return sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )


def _extract_raw_token(message: OutboundEmail) -> str:
    """Extract the reset token from a captured email body."""

    link = next(
        line.strip()
        for line in message.text_body.splitlines()
        if line.startswith("http")
    )

    return parse_qs(
        urlparse(link).query
    )["token"][0]


def test_registered_email_receives_single_use_link() -> None:
    """A matching account receives a reset link; DB stores only its hash."""

    factory = _factory()
    sender = CapturingEmailSender()
    settings = _settings(
        "RESETONE",
        "reset.one@example.com",
    )

    with factory() as session:
        seed_initial_data(session, settings)

        result = PasswordResetService(
            session,
            settings=settings,
            email_sender=sender,
        ).request_reset(
            email="reset.one@example.com",
        )

        assert result.message == GENERIC_RESET_REQUEST_MESSAGE
        assert len(sender.messages) == 1

        raw_token = _extract_raw_token(
            sender.messages[0]
        )
        record = session.scalar(
            select(PasswordResetToken)
        )

        assert record is not None
        assert record.token_hash != raw_token
        assert raw_token not in record.token_hash
        assert record.delivery_status == "sent"


def test_unknown_email_returns_same_generic_response() -> None:
    """Unknown emails must not reveal account existence."""

    factory = _factory()
    sender = CapturingEmailSender()
    settings = _settings(
        "RESETTWO",
        "reset.two@example.com",
    )

    with factory() as session:
        seed_initial_data(session, settings)

        result = PasswordResetService(
            session,
            settings=settings,
            email_sender=sender,
        ).request_reset(
            email="unknown@example.com",
        )

        assert result.message == GENERIC_RESET_REQUEST_MESSAGE
        assert sender.messages == []
        assert session.scalar(
            select(PasswordResetToken)
        ) is None


def test_reset_changes_password_and_token_becomes_used() -> None:
    """The new password works, old password fails, and token is one-use."""

    factory = _factory()
    sender = CapturingEmailSender()
    settings = _settings(
        "RESETTHREE",
        "reset.three@example.com",
    )

    with factory() as session:
        seed_initial_data(session, settings)
        service = PasswordResetService(
            session,
            settings=settings,
            email_sender=sender,
        )

        service.request_reset(
            email="reset.three@example.com",
        )
        raw_token = _extract_raw_token(
            sender.messages[0]
        )

        service.reset_password(
            raw_token=raw_token,
            new_password="NewSecurePassword456!",
        )

        try:
            AuthService(session).authenticate(
                company_code="RESETTHREE",
                login_identifier="resetthreeadmin",
                password="OriginalPassword123!",
            )
        except AuthenticationError:
            pass
        else:
            raise AssertionError(
                "The old password still authenticated."
            )

        current_user = AuthService(session).authenticate(
            company_code="RESETTHREE",
            login_identifier="resetthreeadmin",
            password="NewSecurePassword456!",
        )

        assert current_user.must_change_password is False

        try:
            service.reset_password(
                raw_token=raw_token,
                new_password="AnotherPassword789!",
            )
        except PasswordResetError:
            pass
        else:
            raise AssertionError(
                "A used reset token worked twice."
            )


def test_reset_invalidates_existing_signed_cookie() -> None:
    """The password fingerprint invalidates previously issued cookies."""

    factory = _factory()
    sender = CapturingEmailSender()
    settings = _settings(
        "RESETFOUR",
        "reset.four@example.com",
    )

    with factory() as session:
        seed_initial_data(session, settings)

        current_user = AuthService(session).authenticate(
            company_code="RESETFOUR",
            login_identifier="resetfouradmin",
            password="OriginalPassword123!",
        )

        cookie_service = SignedCookieAuthService(
            session,
            secret_key="test-cookie-secret",
        )
        old_cookie = cookie_service.issue_token(
            current_user
        )

        reset_service = PasswordResetService(
            session,
            settings=settings,
            email_sender=sender,
        )
        reset_service.request_reset(
            email="reset.four@example.com",
        )
        reset_service.reset_password(
            raw_token=_extract_raw_token(
                sender.messages[0]
            ),
            new_password="ChangedPassword789!",
        )

        try:
            cookie_service.restore_user(old_cookie)
        except SignedCookieAuthenticationError:
            pass
        else:
            raise AssertionError(
                "Old signed cookie survived password reset."
            )


def test_expired_reset_link_is_rejected() -> None:
    """Expired links cannot change a password."""

    factory = _factory()
    sender = CapturingEmailSender()
    settings = _settings(
        "RESETFIVE",
        "reset.five@example.com",
    )

    with factory() as session:
        seed_initial_data(session, settings)
        service = PasswordResetService(
            session,
            settings=settings,
            email_sender=sender,
        )
        service.request_reset(
            email="reset.five@example.com",
        )

        record = session.scalar(
            select(PasswordResetToken)
        )
        record.expires_at = (
            record.requested_at
            - timedelta(seconds=1)
        )
        session.commit()

        assert (
            service.is_token_valid(
                _extract_raw_token(
                    sender.messages[0]
                )
            )
            is False
        )


def test_cooldown_does_not_send_repeated_email() -> None:
    """Repeated requests during cooldown return generic success once."""

    factory = _factory()
    sender = CapturingEmailSender()
    settings = _settings(
        "RESETSIX",
        "reset.six@example.com",
    )

    with factory() as session:
        seed_initial_data(session, settings)
        service = PasswordResetService(
            session,
            settings=settings,
            email_sender=sender,
        )

        first = service.request_reset(
            email="reset.six@example.com",
        )
        second = service.request_reset(
            email="reset.six@example.com",
        )

        assert first.message == second.message
        assert len(sender.messages) == 1


def test_same_email_in_multiple_companies_sends_separate_links() -> None:
    """Each active account receives its own company-bound reset link."""

    factory = _factory()
    sender = CapturingEmailSender()

    first_settings = _settings(
        "RESETSEVEN",
        "shared.reset@example.com",
    )
    second_settings = _settings(
        "RESETEIGHT",
        "shared.reset@example.com",
    )

    with factory() as session:
        first = seed_initial_data(
            session,
            first_settings,
        )
        second = seed_initial_data(
            session,
            second_settings,
        )

        service = PasswordResetService(
            session,
            settings=first_settings,
            email_sender=sender,
        )
        service.request_reset(
            email="shared.reset@example.com",
        )

        records = list(
            session.scalars(
                select(PasswordResetToken).order_by(
                    PasswordResetToken.company_id
                )
            ).all()
        )

        assert len(records) == 2
        assert {
            record.company_id
            for record in records
        } == {
            first["company"].id,
            second["company"].id,
        }
        assert len(sender.messages) == 2
        assert "RESETSEVEN Company" in sender.messages[0].text_body
        assert "RESETEIGHT Company" in sender.messages[1].text_body
