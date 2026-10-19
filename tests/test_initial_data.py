"""Initial data and company-isolation tests."""

from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import models  # noqa: F401
from config.settings import Settings
from database.base import Base
from repositories.company_repository import CompanyRepository
from repositories.employee_repository import EmployeeRepository
from schemas.user_schema import EmployeeCreate
from scripts.create_initial_data import seed_initial_data
from services.employee_service import EmployeeService


def _settings() -> Settings:
    """Return isolated test seed settings."""

    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code="TEST",
        initial_company_name="Test Company",
        initial_admin_username="testadmin",
        initial_admin_email="testadmin@example.com",
        initial_admin_password=SecretStr(
            "SecureAdmin123!"
        ),
        initial_admin_employee_number="ADM-001",
        initial_admin_first_name="Test",
        initial_admin_last_name="Administrator",
    )


def test_initial_data_is_idempotent() -> None:
    """Running the seed twice must not duplicate records."""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )
    Base.metadata.create_all(engine)

    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    with factory() as session:
        first = seed_initial_data(
            session,
            _settings(),
        )
        second = seed_initial_data(
            session,
            _settings(),
        )

        assert first["company_created"] is True
        assert first["roles_created"] == 5
        assert first["admin_user_created"] is True
        assert first["admin_employee_created"] is True

        assert second["company_created"] is False
        assert second["roles_created"] == 0
        assert second["admin_user_created"] is False
        assert second["admin_employee_created"] is False


def test_duplicate_full_names_are_allowed() -> None:
    """Employees may share names when employee numbers differ."""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        company = CompanyRepository(session).create(
            {
                "code": "NAMES",
                "name": "Name Test Company",
            }
        )
        service = EmployeeService(session)

        first = service.create_employee(
            EmployeeCreate(
                company_id=company.id,
                employee_number="EMP-001",
                first_name="Alex",
                last_name="Santos",
            )
        )
        second = service.create_employee(
            EmployeeCreate(
                company_id=company.id,
                employee_number="EMP-002",
                first_name="Alex",
                last_name="Santos",
            )
        )

        matches = EmployeeRepository(
            session
        ).find_by_full_name(
            company.id,
            "Alex",
            "Santos",
        )

        assert first.full_name == second.full_name
        assert len(matches) == 2


def test_employee_number_is_unique_per_company() -> None:
    """The same employee number may exist in different companies."""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        company_repository = CompanyRepository(session)
        first_company = company_repository.create(
            {
                "code": "C1",
                "name": "Company One",
            }
        )
        second_company = company_repository.create(
            {
                "code": "C2",
                "name": "Company Two",
            }
        )

        service = EmployeeService(session)

        first = service.create_employee(
            EmployeeCreate(
                company_id=first_company.id,
                employee_number="EMP-100",
                first_name="Jamie",
                last_name="Cruz",
            )
        )
        second = service.create_employee(
            EmployeeCreate(
                company_id=second_company.id,
                employee_number="EMP-100",
                first_name="Jamie",
                last_name="Cruz",
            )
        )

        assert first.company_id != second.company_id
        assert (
            first.employee_number
            == second.employee_number
        )
