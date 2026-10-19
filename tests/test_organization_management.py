"""Tests for company profile, department, and role management."""

from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from config.settings import Settings
from database.base import Base
from repositories.role_repository import RoleRepository
from schemas.organization_schema import (
    CompanyNameUpdate,
    CompanyThemeColorUpdate,
    DepartmentCreate,
    RoleCreateRequest,
)
from scripts.create_initial_data import seed_initial_data
from services.organization_service import OrganizationService


def _settings(
    code: str,
    email: str,
) -> Settings:
    """Create isolated company seed settings."""

    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code=code,
        initial_company_name=f"{code} Company",
        initial_admin_username=f"{code.lower()}admin",
        initial_admin_email=email,
        initial_admin_password=SecretStr(
            "Temporary123!"
        ),
        initial_admin_employee_number=f"{code}-001",
        initial_admin_first_name="System",
        initial_admin_last_name="Administrator",
    )


def _factory():
    """Return a fresh in-memory session factory."""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )
    Base.metadata.create_all(engine)

    return sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )


def test_company_name_update_keeps_company_code() -> None:
    """Updating the display name must not change the tenant code."""

    factory = _factory()

    with factory() as session:
        seed = seed_initial_data(
            session,
            _settings(
                "PROFILE",
                "profile.admin@example.com",
            ),
        )

        company = OrganizationService(
            session
        ).update_company_name(
            CompanyNameUpdate(
                company_id=seed["company"].id,
                name="Updated Company Name",
            )
        )

        assert company.name == "Updated Company Name"
        assert company.code == "PROFILE"


def test_department_names_are_unique_per_company() -> None:
    """Duplicate department names are blocked within one company."""

    factory = _factory()

    with factory() as session:
        seed = seed_initial_data(
            session,
            _settings(
                "DEPT",
                "dept.admin@example.com",
            ),
        )
        service = OrganizationService(session)

        request = DepartmentCreate(
            company_id=seed["company"].id,
            name="Information Technology",
            code="IT",
        )

        service.create_department(request)

        try:
            service.create_department(request)
        except ValueError:
            pass
        else:
            raise AssertionError(
                "Duplicate department name was accepted."
            )


def test_same_department_name_allowed_in_other_company() -> None:
    """Different companies may use the same department name."""

    factory = _factory()

    with factory() as session:
        first = seed_initial_data(
            session,
            _settings(
                "FIRSTORG",
                "first.org@example.com",
            ),
        )
        second = seed_initial_data(
            session,
            _settings(
                "SECONDORG",
                "second.org@example.com",
            ),
        )
        service = OrganizationService(session)

        first_department = service.create_department(
            DepartmentCreate(
                company_id=first["company"].id,
                name="Human Resources",
                code="HR",
            )
        )
        second_department = service.create_department(
            DepartmentCreate(
                company_id=second["company"].id,
                name="Human Resources",
                code="HR",
            )
        )

        assert (
            first_department.company_id
            != second_department.company_id
        )


def test_custom_role_creation_is_company_scoped() -> None:
    """A custom role may be created independently per company."""

    factory = _factory()

    with factory() as session:
        first = seed_initial_data(
            session,
            _settings(
                "ROLEONE",
                "role.one@example.com",
            ),
        )
        second = seed_initial_data(
            session,
            _settings(
                "ROLETWO",
                "role.two@example.com",
            ),
        )
        service = OrganizationService(session)

        first_role = service.create_custom_role(
            RoleCreateRequest(
                company_id=first["company"].id,
                name="Payroll Reviewer",
                description="Reviews payroll records.",
            )
        )
        second_role = service.create_custom_role(
            RoleCreateRequest(
                company_id=second["company"].id,
                name="Payroll Reviewer",
                description="Reviews payroll records.",
            )
        )

        assert first_role.name == "payroll reviewer"
        assert second_role.name == "payroll reviewer"
        assert first_role.company_id != second_role.company_id


def test_system_role_cannot_be_deactivated() -> None:
    """Seeded system roles remain protected."""

    factory = _factory()

    with factory() as session:
        seed = seed_initial_data(
            session,
            _settings(
                "SYSTEM",
                "system.role@example.com",
            ),
        )

        company_admin_role = RoleRepository(
            session
        ).get_by_name(
            seed["company"].id,
            "company_admin",
        )
        assert company_admin_role is not None

        try:
            OrganizationService(
                session
            ).set_role_active_status(
                company_id=seed["company"].id,
                role_id=company_admin_role.id,
                is_active=False,
            )
        except ValueError:
            pass
        else:
            raise AssertionError(
                "System role was allowed to deactivate."
            )


def test_custom_role_can_be_deactivated_when_unused() -> None:
    """An unused custom role may be deactivated safely."""

    factory = _factory()

    with factory() as session:
        seed = seed_initial_data(
            session,
            _settings(
                "CUSTOM",
                "custom.role@example.com",
            ),
        )
        service = OrganizationService(session)

        role = service.create_custom_role(
            RoleCreateRequest(
                company_id=seed["company"].id,
                name="Document Reviewer",
            )
        )

        updated = service.set_role_active_status(
            company_id=seed["company"].id,
            role_id=role.id,
            is_active=False,
        )

        assert updated.is_active is False



def test_company_theme_update_keeps_company_code() -> None:
    """Theme changes must remain company-scoped and preserve tenant ID."""

    factory = _factory()

    with factory() as session:
        seed = seed_initial_data(
            session,
            _settings(
                "THEME",
                "theme.admin@example.com",
            ),
        )

        company = OrganizationService(
            session
        ).update_company_theme_color(
            CompanyThemeColorUpdate(
                company_id=seed["company"].id,
                primary_color="#CC5500",
            )
        )

        assert company.theme_primary_color == "#CC5500"
        assert company.code == "THEME"
