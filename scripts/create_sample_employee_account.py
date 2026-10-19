"""Create one sample employee-only account for local testing.

Run from the project root:

    python scripts/create_sample_employee_account.py

Default test credentials:
- Company code: uses INITIAL_COMPANY_CODE from .env
- Username: employee.test
- Temporary password: Employee123!

Behavior:
- Creates an employee-role login account.
- Creates and links one employee profile.
- Forces password change on first login.
- Is idempotent and does not reset an existing password.
- Does not grant administrator access.

This script is for local development/testing. Production employee accounts
should be created through the protected Employees administration page.
"""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from config.settings import get_settings
from database.session import SessionFactory
from repositories.company_repository import CompanyRepository
from repositories.employee_repository import EmployeeRepository
from repositories.role_repository import RoleRepository
from repositories.user_repository import UserRepository
from schemas.admin_management_schema import EmployeeAccountCreate
from services.admin_management_service import (
    AdminManagementService,
)


SAMPLE_EMPLOYEE_NUMBER = "EMP-TEST-001"
SAMPLE_USERNAME = "employee.test"
SAMPLE_EMAIL = "employee.test@example.com"
SAMPLE_TEMPORARY_PASSWORD = "Employee123!"


def main() -> None:
    """Create or report the sample employee-only account."""

    settings = get_settings()

    with SessionFactory() as session:
        company = CompanyRepository(session).get_by_code(
            settings.initial_company_code
        )

        if company is None:
            raise RuntimeError(
                "The configured company was not found. "
                "Run: python scripts/create_initial_data.py"
            )

        employee_role = RoleRepository(session).get_by_name(
            company.id,
            "employee",
        )

        if employee_role is None or not employee_role.is_active:
            raise RuntimeError(
                "The active employee role was not found."
            )

        existing_user = UserRepository(session).get_by_username(
            company.id,
            SAMPLE_USERNAME,
        )
        existing_employee = (
            EmployeeRepository(session)
            .get_by_employee_number(
                company.id,
                SAMPLE_EMPLOYEE_NUMBER,
            )
        )

        if existing_user is not None or existing_employee is not None:
            if (
                existing_user is None
                or existing_employee is None
                or existing_employee.user_id != existing_user.id
            ):
                raise RuntimeError(
                    "The sample username or employee number already "
                    "exists but is not linked correctly."
                )

            print("Sample employee account already exists.")
            print(f"Company code: {company.code}")
            print(f"Username: {existing_user.username}")
            print(f"Role: {existing_user.role.name}")
            print(
                "Must change password: "
                f"{existing_user.must_change_password}"
            )
            print(
                "The existing password was not changed or reset."
            )
            return

        employee = AdminManagementService(
            session
        ).create_employee_with_optional_account(
            EmployeeAccountCreate(
                company_id=company.id,
                employee_number=SAMPLE_EMPLOYEE_NUMBER,
                first_name="Test",
                last_name="Employee",
                work_email=SAMPLE_EMAIL,
                job_title="Sample Employee",
                create_login_account=True,
                role_id=employee_role.id,
                username=SAMPLE_USERNAME,
                login_email=SAMPLE_EMAIL,
                temporary_password=SAMPLE_TEMPORARY_PASSWORD,
            )
        )

        if employee.user is None:
            raise RuntimeError(
                "The employee login account was not created."
            )

        print("Sample employee-only account created.")
        print(f"Company code: {company.code}")
        print(f"Username: {SAMPLE_USERNAME}")
        print(
            f"Temporary password: {SAMPLE_TEMPORARY_PASSWORD}"
        )
        print(f"Role: {employee.user.role.name}")
        print(
            "Must change password: "
            f"{employee.user.must_change_password}"
        )
        print(
            "Expected portal: Employee Portal only."
        )


if __name__ == "__main__":
    main()
