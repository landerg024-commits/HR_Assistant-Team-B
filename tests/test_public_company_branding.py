"""Company theme coverage for login and public auth pages."""

from datetime import datetime, timedelta, timezone
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
from models.company import Company
from models.password_reset_token import PasswordResetToken
from repositories.company_repository import CompanyRepository
from services.organization_service import OrganizationService


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )
    Base.metadata.create_all(engine)

    return sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code="BRAND",
        initial_company_name="Brand Company",
        initial_admin_username="admin",
        initial_admin_email="admin@brand.example",
        initial_admin_password=SecretStr("Temporary123!"),
        initial_admin_employee_number="ADMIN-001",
        initial_admin_first_name="System",
        initial_admin_last_name="Administrator",
    )


def test_company_repository_public_lookup_is_case_insensitive() -> None:
    factory = _factory()

    with factory() as session:
        company = Company(
            code="BRAND",
            name="Brand Company",
            theme_primary_color="#E11D48",
            is_active=True,
        )
        session.add(company)
        session.commit()

        found = CompanyRepository(
            session
        ).get_active_by_code("brand")

        assert found is not None
        assert found.id == company.id
        assert found.theme_primary_color == "#E11D48"


def test_single_active_company_is_public_brand_fallback() -> None:
    factory = _factory()

    with factory() as session:
        company = Company(
            code="ONLY",
            name="Only Company",
            theme_primary_color="#0F766E",
            is_active=True,
        )
        session.add(company)
        session.commit()

        resolved = OrganizationService(
            session
        ).resolve_public_company(None)

        assert resolved is not None
        assert resolved.id == company.id


def test_multiple_companies_require_matching_code() -> None:
    factory = _factory()

    with factory() as session:
        session.add_all(
            [
                Company(
                    code="FIRST",
                    name="First Company",
                    theme_primary_color="#4338E8",
                    is_active=True,
                ),
                Company(
                    code="SECOND",
                    name="Second Company",
                    theme_primary_color="#DC2626",
                    is_active=True,
                ),
            ]
        )
        session.commit()

        service = OrganizationService(session)

        assert (
            service.resolve_public_company(
                "UNKNOWN"
            )
            is None
        )
        assert (
            service.resolve_public_company(
                "second"
            ).theme_primary_color
            == "#DC2626"
        )


def test_valid_reset_token_resolves_company_brand() -> None:
    factory = _factory()

    with factory() as session:
        company = Company(
            code="RESETBRAND",
            name="Reset Brand Company",
            theme_primary_color="#B45309",
            is_active=True,
        )
        session.add(company)
        session.flush()

        raw_token = "valid-public-brand-token"
        record = PasswordResetToken(
            company_id=company.id,
            user_id=999,
            token_hash=(
                PasswordResetService._token_hash(
                    raw_token
                )
            ),
            delivery_email="employee@example.com",
            requested_at=datetime.now(timezone.utc),
            expires_at=(
                datetime.now(timezone.utc)
                + timedelta(minutes=30)
            ),
            delivery_status="sent",
        )
        session.add(record)
        session.commit()

        resolved = (
            PasswordResetService
            .get_company_for_valid_token(
                session,
                raw_token,
            )
        )

        assert resolved is not None
        assert resolved.id == company.id
        assert resolved.theme_primary_color == "#B45309"


def test_app_applies_public_company_color_to_auth_pages() -> None:
    source = (
        PROJECT_ROOT / "app.py"
    ).read_text(encoding="utf-8")

    assert "def _load_public_company_brand(" in source
    assert "public_primary_color" in source
    assert (
        "apply_theme(\n"
        "            primary_color=public_primary_color"
        in source
    )
    assert "render_login_layout(" in source
    assert "render_forgot_password_layout(" in source
    assert "render_reset_password_layout(" in source


def test_login_company_code_is_inside_single_submit_form() -> None:
    source = (
        PROJECT_ROOT
        / "ui/pages/authentication/login_page.py"
    ).read_text(encoding="utf-8")

    company_input_position = source.index(
        'company_code = st.text_input('
    )
    form_position = source.index(
        'with st.form(\n'
        '            "login_form"'
    )

    assert form_position < company_input_position
    assert 'key="login_company_code"' in source
    assert "on_change=_sync_public_company_code" not in source
    assert "all credentials in one form" in source


def test_auth_layout_uses_resolved_company_name() -> None:
    source = (
        PROJECT_ROOT
        / "ui/layouts/auth_layout.py"
    ).read_text(encoding="utf-8")

    assert "company_name: str" in source
    assert "company_name=company_name" in source
    assert "default_company_code: str" in source


def test_logout_preserves_company_code_for_login_branding() -> None:
    source = (
        PROJECT_ROOT
        / "authentication/session_manager.py"
    ).read_text(encoding="utf-8")

    logout = source.split(
        "def logout(cls)",
        1,
    )[1].split(
        "def clear_after_password_reset",
        1,
    )[0]

    assert '"public_company_code"' in logout
    assert "current_user.company_code" in logout
    assert 'st.query_params[\n                "company"\n            ]' in logout


def test_reset_email_link_contains_company_code() -> None:
    source = (
        PROJECT_ROOT
        / "authentication/password_reset_service.py"
    ).read_text(encoding="utf-8")

    assert '"company": company_code' in source
    assert "company_code=user.company.code" in source


def test_public_branding_does_not_change_email_only_forgot_form() -> None:
    source = (
        PROJECT_ROOT
        / "ui/pages/authentication/forgot_password_page.py"
    ).read_text(encoding="utf-8")

    assert "Company Code" not in source
    assert "Registered Login Email" in source
