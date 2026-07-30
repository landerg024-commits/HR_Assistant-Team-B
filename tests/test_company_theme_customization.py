"""Tests for company-specific customizable theme colors."""

from pathlib import Path

from pydantic import SecretStr, ValidationError
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from config.settings import Settings
from core.constants import DEFAULT_COMPANY_THEME_COLOR
from database.base import Base
from database.schema_upgrade import upgrade_existing_schema
from schemas.organization_schema import CompanyThemeColorUpdate
from scripts.create_initial_data import seed_initial_data
from services.organization_service import OrganizationService
from ui.theme.color_palette import build_accent_palette


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _settings(code: str, email: str) -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code=code,
        initial_company_name=f"{code} Company",
        initial_admin_username=f"{code.lower()}admin",
        initial_admin_email=email,
        initial_admin_password=SecretStr("Temporary123!"),
        initial_admin_employee_number=f"{code}-001",
        initial_admin_first_name="System",
        initial_admin_last_name="Administrator",
    )


def _factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    return sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )


def test_company_theme_color_is_tenant_scoped() -> None:
    factory = _factory()

    with factory() as session:
        first = seed_initial_data(
            session,
            _settings("BLUEORG", "blue@example.com"),
        )
        second = seed_initial_data(
            session,
            _settings("GREENORG", "green@example.com"),
        )
        service = OrganizationService(session)

        updated = service.update_company_theme_color(
            CompanyThemeColorUpdate(
                company_id=first["company"].id,
                primary_color="#0066CC",
            )
        )

        second_company = service.get_company(
            second["company"].id
        )

        assert updated.theme_primary_color == "#0066CC"
        assert (
            second_company.theme_primary_color
            == DEFAULT_COMPANY_THEME_COLOR
        )


def test_theme_schema_rejects_invalid_hex() -> None:
    try:
        CompanyThemeColorUpdate(
            company_id=1,
            primary_color="blue",
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("Invalid theme color was accepted.")


def test_palette_supports_light_and_dark_colors() -> None:
    yellow = build_accent_palette("#FFD400")
    navy = build_accent_palette("#071A52")

    assert yellow["primary"] == "#FFD400"
    assert yellow["on_primary"] == "#10172A"
    assert navy["on_primary"] == "#FFFFFF"

    for palette in [yellow, navy]:
        assert palette["primary_hover"].startswith("#")
        assert palette["primary_soft"].startswith("#")
        assert palette["primary_text"].startswith("#")
        assert len(palette["primary_rgb"].split(",")) == 3


def test_legacy_company_table_receives_theme_column() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE companies (
                    id INTEGER PRIMARY KEY,
                    code VARCHAR(50) NOT NULL,
                    name VARCHAR(200) NOT NULL,
                    is_active BOOLEAN NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO companies (
                    id, code, name, is_active
                ) VALUES (
                    1, 'LEGACY', 'Legacy Company', 1
                )
                """
            )
        )

    upgrade_existing_schema(engine)

    columns = {
        item["name"]
        for item in inspect(engine).get_columns("companies")
    }

    assert "theme_primary_color" in columns

    with engine.connect() as connection:
        value = connection.execute(
            text(
                "SELECT theme_primary_color "
                "FROM companies WHERE id = 1"
            )
        ).scalar_one()

    assert value == DEFAULT_COMPANY_THEME_COLOR


def test_company_profile_has_picker_preview_save_and_reset() -> None:
    source = (
        PROJECT_ROOT
        / "ui/pages/admin/company_page.py"
    ).read_text(encoding="utf-8")

    assert "st.color_picker(" in source
    assert '"Save Theme Color"' in source
    assert '"Reset to Default Violet"' in source
    assert "build_accent_palette" in source
    assert "Primary Action" in source
    assert "Hover State" in source
    assert "Soft Accent" in source


def test_authenticated_app_loads_company_theme() -> None:
    source = (
        PROJECT_ROOT / "app.py"
    ).read_text(encoding="utf-8")

    assert "def _load_company_theme_color(" in source
    assert "current_user.company_id" in source
    assert "apply_theme(" in source
    assert "primary_color=_load_company_theme_color(" in source


def test_theme_loader_uses_dynamic_accessible_variables() -> None:
    source = (
        PROJECT_ROOT
        / "ui/theme/theme_loader.py"
    ).read_text(encoding="utf-8")

    palette_source = (
        PROJECT_ROOT
        / "ui/theme/color_palette.py"
    ).read_text(encoding="utf-8")

    assert "def build_accent_palette(" in palette_source
    assert "--hr-primary-text:" in source
    assert "--hr-on-primary:" in source
    assert "--hr-primary-rgb:" in source
    assert "COMPANY ACCENT CONTRAST — v8.5.1" in source
    assert "const primaryColor = '__PRIMARY__';" in source
    assert "const onPrimary = '__ON_PRIMARY__';" in source
    assert "_enforce_input_value_contrast(tokens)" in source


def test_notification_trigger_is_part_of_company_theme_palette() -> None:
    source = (
        PROJECT_ROOT
        / "ui/theme/theme_loader.py"
    ).read_text(encoding="utf-8")

    block = source.split(
        "NOTIFICATION TRIGGER COMPANY THEME — v8.7.1",
        1,
    )[1]

    assert "var(--hr-primary)" in block
    assert "var(--hr-on-primary)" in block
    assert "rgba(var(--hr-primary-rgb)" in block
