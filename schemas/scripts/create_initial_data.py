r"""Create the initial company, system roles, admin user, and employee.

Purpose:
- Prepare a new database for first-time use.
- Allow repeated execution without creating duplicate rows.
- Keep setup values configurable through `.env`.

Run:
    python scripts\create_initial_data.py
"""

from pathlib import Path
import sys

from sqlalchemy.orm import Session


# When a Python file inside scripts/ is executed directly, Python initially
# searches scripts/ instead of the project root. Add the root so imports such
# as config.settings and database.session work correctly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from config.settings import Settings, get_settings
from core.constants import (
    SYSTEM_ROLES,
    SYSTEM_ROLE_DESCRIPTIONS,
)
from database.connection_manager import DatabaseConnectionManager
from database.session import SessionFactory
from repositories.company_repository import CompanyRepository
from repositories.employee_repository import EmployeeRepository
from repositories.user_repository import UserRepository
from schemas.role_schema import RoleCreate
from schemas.user_schema import EmployeeCreate, UserCreate
from services.employee_service import EmployeeService
from services.role_service import RoleService
from services.user_service import UserService


def seed_initial_data(
    session: Session,
    settings: Settings,
) -> dict[str, object]:
    """Create initial records only when they do not already exist."""

    # ---------------------------------------------------------
    # 1. COMPANY
    # ---------------------------------------------------------
    company_repository = CompanyRepository(session)
    company = company_repository.get_by_code(
        settings.initial_company_code
    )
    company_created = False

    if company is None:
        company = company_repository.create(
            {
                "code": settings.initial_company_code,
                "name": settings.initial_company_name,
                "is_active": True,
            }
        )
        company_created = True

    # ---------------------------------------------------------
    # 2. SYSTEM ROLES
    # ---------------------------------------------------------
    role_service = RoleService(session)
    roles_created = 0
    role_records = {}

    for role_name in SYSTEM_ROLES:
        role, was_created = role_service.get_or_create_role(
            RoleCreate(
                company_id=company.id,
                name=role_name,
                description=SYSTEM_ROLE_DESCRIPTIONS[
                    role_name
                ],
                is_system_role=True,
            )
        )

        role_records[role_name] = role

        if was_created:
            roles_created += 1

    # The first administrator belongs to this company.
    admin_role = role_records["company_admin"]

    # ---------------------------------------------------------
    # 3. INITIAL ADMIN USER
    # ---------------------------------------------------------
    user_repository = UserRepository(session)
    admin_user = user_repository.get_by_username(
        company.id,
        settings.initial_admin_username,
    )
    admin_user_created = False

    if admin_user is None:
        user_service = UserService(session)
        admin_user = user_service.create_user(
            UserCreate(
                company_id=company.id,
                role_id=admin_role.id,
                username=settings.initial_admin_username,
                email=settings.initial_admin_email,
                password=(
                    settings.initial_admin_password
                    .get_secret_value()
                ),
            ),
            must_change_password=True,
        )
        admin_user_created = True

    # ---------------------------------------------------------
    # 4. INITIAL ADMIN EMPLOYEE PROFILE
    # ---------------------------------------------------------
    employee_repository = EmployeeRepository(session)
    admin_employee = (
        employee_repository.get_by_employee_number(
            company.id,
            settings.initial_admin_employee_number,
        )
    )
    admin_employee_created = False

    if admin_employee is None:
        employee_service = EmployeeService(session)
        admin_employee = employee_service.create_employee(
            EmployeeCreate(
                company_id=company.id,
                user_id=admin_user.id,
                employee_number=(
                    settings.initial_admin_employee_number
                ),
                first_name=(
                    settings.initial_admin_first_name
                ),
                last_name=(
                    settings.initial_admin_last_name
                ),
                work_email=settings.initial_admin_email,
                job_title="Company Administrator",
            )
        )
        admin_employee_created = True

    # Return records and flags for tests and status messages.
    return {
        "company": company,
        "company_created": company_created,
        "roles_created": roles_created,
        "admin_user": admin_user,
        "admin_user_created": admin_user_created,
        "admin_employee": admin_employee,
        "admin_employee_created": admin_employee_created,
    }


def main() -> None:
    """Create tables, seed records, and print a setup summary."""

    settings = get_settings()

    # Ensure the configured database works before inserting data.
    connection_manager = DatabaseConnectionManager()
    connection_manager.test_connection()
    connection_manager.create_tables()

    # A context manager guarantees the session closes after setup.
    with SessionFactory() as session:
        result = seed_initial_data(
            session,
            settings,
        )

    print("Initial data setup completed.")
    print(
        "Company: "
        f"{result['company'].code} - "
        f"{result['company'].name}"
    )
    print(f"Company created: {result['company_created']}")
    print(f"Roles created: {result['roles_created']}")
    print(f"Admin user: {result['admin_user'].username}")
    print(
        "Admin user created: "
        f"{result['admin_user_created']}"
    )
    print(
        "Admin employee number: "
        f"{result['admin_employee'].employee_number}"
    )
    print(
        "Admin employee created: "
        f"{result['admin_employee_created']}"
    )
    print(
        "Admin must change password: "
        f"{result['admin_user'].must_change_password}"
    )


if __name__ == "__main__":
    main()
