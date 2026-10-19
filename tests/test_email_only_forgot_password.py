"""Tests for the email-only Forgot Password user experience."""

from pathlib import Path

from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from authentication.password_reset_service import (
    PasswordResetService,
)
from config.settings import Settings
from database.base import Base
from integrations.email.email_sender import OutboundEmail
from scripts.create_initial_data import seed_initial_data


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CapturingSender:
    """Capture reset emails without using a network."""

    def __init__(self) -> None:
        self.messages: list[OutboundEmail] = []

    def send(self, message: OutboundEmail) -> str:
        self.messages.append(message)
        return "captured"


def _settings(
    code: str,
    email: str,
) -> Settings:
    """Return isolated company settings."""

    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code=code,
        initial_company_name=f"{code} Company",
        initial_admin_username=f"{code.lower()}admin",
        initial_admin_email=email,
        initial_admin_password=SecretStr("Password123!"),
        initial_admin_employee_number=f"{code}-001",
        initial_admin_first_name="System",
        initial_admin_last_name="Administrator",
        password_reset_request_cooldown_seconds=60,
    )


def test_forgot_password_page_has_email_only() -> None:
    """The public form must not request a company code."""

    source = (
        PROJECT_ROOT
        / "ui/pages/authentication/forgot_password_page.py"
    ).read_text(encoding="utf-8")

    assert '"Registered Login Email"' in source
    assert '"Company Code"' not in source
    assert "default_company_code" not in source
    assert "company_code=" not in source


def test_forgot_password_schema_has_no_company_code() -> None:
    """Public reset validation must contain only the email identity."""

    source = (
        PROJECT_ROOT
        / "schemas/auth_schema.py"
    ).read_text(encoding="utf-8")

    block = source.split(
        "class ForgotPasswordRequest",
        1,
    )[1].split(
        "class PasswordResetCompletionRequest",
        1,
    )[0]

    assert "email: EmailStr" in block
    assert "company_code" not in block


def test_single_email_finds_account_without_company_code() -> None:
    """The reset service must discover the company internally."""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )
    settings = _settings(
        "EMAILONLY",
        "employee.reset@example.com",
    )
    sender = CapturingSender()

    with factory() as session:
        seed_initial_data(session, settings)

        PasswordResetService(
            session,
            settings=settings,
            email_sender=sender,
        ).request_reset(
            email="employee.reset@example.com",
        )

        assert len(sender.messages) == 1
        assert (
            sender.messages[0].to_email
            == "employee.reset@example.com"
        )
        assert "EMAILONLY Company" in (
            sender.messages[0].text_body
        )
