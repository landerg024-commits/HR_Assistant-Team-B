"""Behavior tests for Employee Master Record onboarding."""

from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from config.settings import Settings
from database.base import Base
from schemas.admin_management_schema import (
    EmployeeAccountCreate,
)
from scripts.create_initial_data import seed_initial_data
from services.admin_management_service import (
    AdminManagementService,
)


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code="ONBOARD",
        initial_company_name="Onboarding Company",
        initial_admin_username="admin",
        initial_admin_email="admin.onboard@example.com",
        initial_admin_password=SecretStr("Temporary123!"),
        initial_admin_employee_number="ADMIN-001",
        initial_admin_first_name="System",
        initial_admin_last_name="Administrator",
    )


def test_create_form_values_produce_linked_user() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    with factory() as session:
        seed = seed_initial_data(session, _settings())

        employee = AdminManagementService(
            session
        ).create_employee_with_optional_account(
            EmployeeAccountCreate(
                company_id=seed["company"].id,
                employee_number="EMP-001",
                first_name="Alex",
                last_name="Santos",
                work_email="alex@example.com",
                create_login_account=True,
                username="alex.santos",
                login_email="alex@example.com",
                temporary_password="Temporary456!",
                clearance=2,
            )
        )

        assert employee.user is not None
        assert employee.user.clearance == 2
        assert employee.user.must_change_password is True
