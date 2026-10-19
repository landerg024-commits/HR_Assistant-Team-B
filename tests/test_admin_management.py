"""Tests for administrator user and employee management."""

from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import models  # noqa: F401
from config.settings import Settings
from database.base import Base
from repositories.role_repository import RoleRepository
from schemas.admin_management_schema import EmployeeAccountCreate
from scripts.create_initial_data import seed_initial_data
from services.admin_management_service import AdminManagementService


def _settings(company_code: str, email: str) -> Settings:
    """Return valid isolated seed settings."""
    return Settings(
        _env_file=None,
        database_url='sqlite+pysqlite:///:memory:',
        initial_company_code=company_code,
        initial_company_name=f'{company_code} Company',
        initial_admin_username=f'{company_code.lower()}admin',
        initial_admin_email=email,
        initial_admin_password=SecretStr('Temporary123!'),
        initial_admin_employee_number=f'{company_code}-001',
        initial_admin_first_name='System',
        initial_admin_last_name='Administrator',
    )


def _factory():
    """Create a fresh in-memory database."""
    engine = create_engine('sqlite+pysqlite:///:memory:')
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_create_employee_with_login_account() -> None:
    """Create linked employee and user records."""
    factory = _factory()
    with factory() as session:
        seed = seed_initial_data(session, _settings('ONE', 'admin.one@example.com'))
        employee_role = RoleRepository(session).get_by_name(seed['company'].id, 'employee')
        assert employee_role is not None

        employee = AdminManagementService(session).create_employee_with_optional_account(
            EmployeeAccountCreate(
                company_id=seed['company'].id,
                employee_number='EMP-100',
                first_name='Alex',
                last_name='Santos',
                work_email='alex.santos@example.com',
                create_login_account=True,
                role_id=employee_role.id,
                username='alex.santos',
                login_email='alex.login@example.com',
                temporary_password='Temporary456!',
            )
        )
        assert employee.user is not None
        assert employee.user.username == 'alex.santos'
        assert employee.user.must_change_password is True


def test_duplicate_full_names_remain_allowed() -> None:
    """Allow duplicate names when employee numbers differ."""
    factory = _factory()
    with factory() as session:
        seed = seed_initial_data(session, _settings('TWO', 'admin.two@example.com'))
        service = AdminManagementService(session)
        for number in ('EMP-001', 'EMP-002'):
            service.create_employee_with_optional_account(
                EmployeeAccountCreate(
                    company_id=seed['company'].id,
                    employee_number=number,
                    first_name='Jamie',
                    last_name='Cruz',
                )
            )
        matches = [
            employee
            for employee in service.list_employees(seed['company'].id)
            if employee.full_name == 'Jamie Cruz'
        ]
        assert len(matches) == 2


def test_company_user_lists_are_isolated() -> None:
    """One company cannot see another company's user accounts."""
    factory = _factory()
    with factory() as session:
        first = seed_initial_data(session, _settings('FIRST', 'admin.first@example.com'))
        second = seed_initial_data(session, _settings('SECOND', 'admin.second@example.com'))
        service = AdminManagementService(session)
        first_users = service.list_users(first['company'].id)
        second_users = service.list_users(second['company'].id)
        assert len(first_users) == 1
        assert len(second_users) == 1
        assert first_users[0].company_id != second_users[0].company_id


def test_current_admin_cannot_deactivate_self() -> None:
    """Protect the current administrator from self-deactivation."""
    factory = _factory()
    with factory() as session:
        seed = seed_initial_data(session, _settings('SAFE', 'admin.safe@example.com'))
        service = AdminManagementService(session)
        try:
            service.set_user_active_status(
                company_id=seed['company'].id,
                user_id=seed['admin_user'].id,
                is_active=False,
                current_user_id=seed['admin_user'].id,
            )
        except ValueError:
            pass
        else:
            raise AssertionError('Current admin was allowed to deactivate itself.')
