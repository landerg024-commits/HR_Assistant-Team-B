"""Tests for real SMTP email integration status and test delivery."""

from pydantic import SecretStr

from config.settings import Settings
from integrations.email.email_sender import (
    EmailDeliveryError,
    OutboundEmail,
)
from services.email_integration_service import (
    EmailIntegrationService,
)


class CapturingSender:
    """In-memory sender for test-email assertions."""

    def __init__(self) -> None:
        self.messages: list[OutboundEmail] = []

    def send(self, message: OutboundEmail) -> str:
        self.messages.append(message)
        return "captured-smtp"


def _settings(
    *,
    mode: str,
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
) -> Settings:
    """Return isolated email settings."""

    return Settings(
        _env_file=None,
        email_delivery_mode=mode,
        smtp_host=host,
        smtp_port=587,
        smtp_username=username,
        smtp_password=(
            SecretStr(password)
            if password is not None
            else None
        ),
        smtp_from_email=(
            username or "no-reply@example.com"
        ),
        smtp_from_name="Test HR",
        smtp_use_starttls=True,
        smtp_use_ssl=False,
        password_reset_base_url=(
            "https://hr.example.com"
        ),
    )


def test_local_mode_is_not_internet_ready() -> None:
    """Local outbox must not be reported as real internet delivery."""

    status = EmailIntegrationService(
        settings=_settings(mode="local")
    ).get_status()

    assert status.internet_delivery_ready is False
    assert status.mode == "local"


def test_complete_smtp_configuration_is_ready() -> None:
    """All required SMTP values produce a ready status."""

    status = EmailIntegrationService(
        settings=_settings(
            mode="smtp",
            host="smtp.example.com",
            username="sender@example.com",
            password="secret",
        )
    ).get_status()

    assert status.internet_delivery_ready is True
    assert status.host == "smtp.example.com"
    assert status.port == 587
    assert status.encryption == "STARTTLS"
    assert status.username_configured is True


def test_missing_smtp_password_is_not_ready() -> None:
    """SMTP mode without a password must remain disabled."""

    status = EmailIntegrationService(
        settings=_settings(
            mode="smtp",
            host="smtp.example.com",
            username="sender@example.com",
            password=None,
        )
    ).get_status()

    assert status.internet_delivery_ready is False


def test_send_test_email_uses_configured_sender() -> None:
    """Administrator test mail must use the real adapter contract."""

    sender = CapturingSender()
    service = EmailIntegrationService(
        settings=_settings(
            mode="smtp",
            host="smtp.example.com",
            username="sender@example.com",
            password="secret",
        ),
        email_sender=sender,
    )

    result = service.send_test_email(
        "recipient@example.com"
    )

    assert result.recipient == "recipient@example.com"
    assert result.delivery_reference == "captured-smtp"
    assert len(sender.messages) == 1
    assert (
        sender.messages[0].to_email
        == "recipient@example.com"
    )
    assert "email delivery test" in (
        sender.messages[0].subject.lower()
    )


def test_send_test_email_rejects_local_mode() -> None:
    """A local outbox cannot pass an internet-delivery test."""

    service = EmailIntegrationService(
        settings=_settings(mode="local"),
        email_sender=CapturingSender(),
    )

    try:
        service.send_test_email(
            "recipient@example.com"
        )
    except EmailDeliveryError as error:
        assert "not fully configured" in str(error)
    else:
        raise AssertionError(
            "Local mode passed the SMTP test."
        )


def test_send_test_email_validates_recipient() -> None:
    """Invalid recipient values must not reach the adapter."""

    service = EmailIntegrationService(
        settings=_settings(
            mode="smtp",
            host="smtp.example.com",
            username="sender@example.com",
            password="secret",
        ),
        email_sender=CapturingSender(),
    )

    try:
        service.send_test_email("not-an-email")
    except EmailDeliveryError as error:
        assert "valid test recipient" in str(error)
    else:
        raise AssertionError(
            "Invalid recipient was accepted."
        )
