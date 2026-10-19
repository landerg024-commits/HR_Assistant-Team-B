"""Email delivery adapters for password-reset messages.

Production uses SMTP. Local development writes RFC-compatible `.eml` files
to a private outbox so the reset flow can be tested without external email.
"""

from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
import smtplib
import ssl
from typing import Protocol
from uuid import uuid4

from config.settings import Settings


class EmailDeliveryError(RuntimeError):
    """Raised internally when an email cannot be delivered."""


@dataclass(frozen=True, slots=True)
class EmailAttachment:
    """One binary attachment included in an outbound message."""

    filename: str
    content: bytes
    mime_type: str = "application/octet-stream"


@dataclass(slots=True)
class OutboundEmail:
    """Provider-independent email content."""

    to_email: str
    subject: str
    text_body: str
    cc_emails: tuple[str, ...] = ()
    attachments: tuple[EmailAttachment, ...] = ()


class EmailSender(Protocol):
    """Contract implemented by local and SMTP email adapters."""

    def send(self, message: OutboundEmail) -> str:
        """Deliver a message and return an internal delivery reference."""


def _safe_header(value: str) -> str:
    """Prevent CR/LF header injection."""

    return value.replace("\r", " ").replace("\n", " ").strip()


def _build_message(
    *,
    message: OutboundEmail,
    settings: Settings,
) -> EmailMessage:
    """Build one standards-compliant plain-text email."""

    email_message = EmailMessage()
    email_message["To"] = _safe_header(message.to_email)

    if message.cc_emails:
        email_message["Cc"] = ", ".join(
            _safe_header(value)
            for value in message.cc_emails
            if value.strip()
        )

    email_message["From"] = (
        f"{_safe_header(settings.smtp_from_name)} "
        f"<{_safe_header(settings.smtp_from_email)}>"
    )
    email_message["Subject"] = _safe_header(message.subject)
    email_message.set_content(message.text_body)

    for attachment in message.attachments:
        mime_type = (attachment.mime_type or "application/octet-stream").split(";", 1)[0].strip()
        if "/" in mime_type:
            maintype, subtype = mime_type.split("/", 1)
        else:
            maintype, subtype = "application", "octet-stream"

        email_message.add_attachment(
            attachment.content,
            maintype=maintype,
            subtype=subtype,
            filename=_safe_header(attachment.filename),
        )

    return email_message


class LocalOutboxEmailSender:
    """Write development email messages to a private local directory."""

    def __init__(
        self,
        settings: Settings,
    ) -> None:
        self.settings = settings
        self.outbox_dir = Path(
            settings.password_reset_outbox_dir
        ).resolve()
        self.outbox_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    def send(self, message: OutboundEmail) -> str:
        """Write one `.eml` file without exposing it in the UI."""

        email_message = _build_message(
            message=message,
            settings=self.settings,
        )

        filename = (
            f"password_reset_{uuid4().hex}.eml"
        )
        destination = self.outbox_dir / filename
        destination.write_bytes(
            email_message.as_bytes()
        )

        return str(destination)


class SmtpEmailSender:
    """Send reset messages through a configured SMTP server."""

    def __init__(
        self,
        settings: Settings,
    ) -> None:
        self.settings = settings

        if not (settings.smtp_host or "").strip():
            raise EmailDeliveryError(
                "SMTP_HOST is required in smtp email mode."
            )

        if (
            settings.smtp_use_ssl
            and settings.smtp_use_starttls
        ):
            raise EmailDeliveryError(
                "Enable either SMTP_USE_SSL or "
                "SMTP_USE_STARTTLS, not both."
            )

    def send(self, message: OutboundEmail) -> str:
        """Connect, optionally authenticate, and send one email."""

        email_message = _build_message(
            message=message,
            settings=self.settings,
        )
        context = ssl.create_default_context()

        try:
            if self.settings.smtp_use_ssl:
                smtp = smtplib.SMTP_SSL(
                    self.settings.smtp_host,
                    self.settings.smtp_port,
                    timeout=self.settings.smtp_timeout_seconds,
                    context=context,
                )
            else:
                smtp = smtplib.SMTP(
                    self.settings.smtp_host,
                    self.settings.smtp_port,
                    timeout=self.settings.smtp_timeout_seconds,
                )

            with smtp:
                smtp.ehlo()

                if self.settings.smtp_use_starttls:
                    smtp.starttls(context=context)
                    smtp.ehlo()

                username = (
                    self.settings.smtp_username or ""
                ).strip()
                password = (
                    self.settings.smtp_password.get_secret_value()
                    if self.settings.smtp_password is not None
                    else ""
                )

                if username:
                    smtp.login(username, password)

                smtp.send_message(email_message)

        except Exception as error:
            # Expose only the exception class, never credentials or raw
            # provider responses that may contain sensitive information.
            raise EmailDeliveryError(
                "SMTP delivery failed "
                f"({type(error).__name__}). Check the host, port, "
                "encryption mode, account permission, username, "
                "password/app password, and network connection."
            ) from error

        return "smtp"


def build_email_sender(
    settings: Settings,
) -> EmailSender:
    """Return the configured email adapter."""

    mode = settings.email_delivery_mode.strip().lower()

    if mode == "local":
        return LocalOutboxEmailSender(settings)

    if mode == "smtp":
        return SmtpEmailSender(settings)

    raise EmailDeliveryError(
        "EMAIL_DELIVERY_MODE must be local or smtp."
    )
