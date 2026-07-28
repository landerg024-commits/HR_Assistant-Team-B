"""Tests for local password-reset email and admin fallback."""

from pathlib import Path

from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from authentication.auth_service import (
    AuthenticationError,
    AuthService,
)
from authentication.password_reset_service import (
    PasswordResetService,
)
from config.settings import Settings
from database.base import Base
from integrations.email.email_sender import (
    LocalOutboxEmailSender,
    OutboundEmail,
)
from scripts.create_initial_data import seed_initial_data


def _settings(
    *,
    outbox: Path,
) -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code="ADMINRESET",
        initial_company_name="Admin Reset Company",
        initial_admin_username="admin",
        initial_admin_email="admin.reset@example.com",
        initial_admin_password=SecretStr(
            "OriginalPassword123!"
        ),
        initial_admin_employee_number="ADMIN-001",
        initial_admin_first_name="System",
        initial_admin_last_name="Administrator",
        password_reset_outbox_dir=str(outbox),
        email_delivery_mode="local",
    )


def test_local_outbox_writes_eml_file(
    tmp_path: Path,
) -> None:
    """Development mode writes the reset link to a private email file."""

    settings = _settings(outbox=tmp_path)
    sender = LocalOutboxEmailSender(settings)

    reference = sender.send(
        OutboundEmail(
            to_email="employee@example.com",
            subject="Reset password",
            text_body=(
                "Open http://localhost:8501/"
                "?auth=reset&token=secret"
            ),
        )
    )

    path = Path(reference)

    assert path.is_file()
    content = path.read_text(
        encoding="utf-8",
        errors="replace",
    )
    assert "employee@example.com" in content
    assert "auth=reset" in content


def test_admin_sets_temporary_password_and_forces_change(
    tmp_path: Path,
) -> None:
    """Admin fallback replaces, never retrieves, the old password."""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )
    settings = _settings(outbox=tmp_path)

    with factory() as session:
        seed = seed_initial_data(session, settings)

        # Add a second company account by reusing the employee role.
        from repositories.role_repository import RoleRepository
        from schemas.user_schema import UserCreate
        from services.user_service import UserService

        employee_role = RoleRepository(
            session
        ).get_by_name(
            seed["company"].id,
            "employee",
        )

        employee_user = UserService(session).create_user(
            UserCreate(
                company_id=seed["company"].id,
                role_id=employee_role.id,
                username="employee.user",
                email="employee.user@example.com",
                password="EmployeeOld123!",
            ),
            must_change_password=False,
        )

        PasswordResetService(
            session,
            settings=settings,
            email_sender=LocalOutboxEmailSender(
                settings
            ),
        ).set_temporary_password_by_admin(
            company_id=seed["company"].id,
            user_id=employee_user.id,
            current_admin_user_id=seed["admin_user"].id,
            temporary_password="TemporaryNew456!",
        )

        try:
            AuthService(session).authenticate(
                company_code="ADMINRESET",
                login_identifier="employee.user",
                password="EmployeeOld123!",
            )
        except AuthenticationError:
            pass
        else:
            raise AssertionError(
                "Old employee password still worked."
            )

        current_user = AuthService(session).authenticate(
            company_code="ADMINRESET",
            login_identifier="employee.user",
            password="TemporaryNew456!",
        )

        assert current_user.must_change_password is True
