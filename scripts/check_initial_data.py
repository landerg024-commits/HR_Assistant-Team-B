"""Verify that required initial data exists and is linked correctly."""

from pathlib import Path
import sys


# Allow direct execution from the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from config.settings import get_settings
from core.constants import SYSTEM_ROLES
from database.session import SessionFactory
from repositories.company_repository import CompanyRepository
from repositories.employee_repository import EmployeeRepository
from repositories.role_repository import RoleRepository
from repositories.user_repository import UserRepository


def main() -> None:
    """Check the company, roles, admin user, and employee link."""

    settings = get_settings()

    with SessionFactory() as session:
        # Check the initial company.
        company = CompanyRepository(
            session
        ).get_by_code(settings.initial_company_code)

        if company is None:
            raise SystemExit(
                "Initial company was not found."
            )

        # Check every required system role.
        role_repository = RoleRepository(session)
        missing_roles = [
            role_name
            for role_name in SYSTEM_ROLES
            if role_repository.get_by_name(
                company.id,
                role_name,
            )
            is None
        ]

        if missing_roles:
            raise SystemExit(
                "Missing roles: "
                + ", ".join(missing_roles)
            )

        # Check the initial administrator login account.
        admin_user = UserRepository(
            session
        ).get_by_username(
            company.id,
            settings.initial_admin_username,
        )

        if admin_user is None:
            raise SystemExit(
                "Initial admin user was not found."
            )

        # Check the linked employee profile.
        admin_employee = EmployeeRepository(
            session
        ).get_by_employee_number(
            company.id,
            settings.initial_admin_employee_number,
        )

        if admin_employee is None:
            raise SystemExit(
                "Initial admin employee was not found."
            )

        if admin_employee.user_id != admin_user.id:
            raise SystemExit(
                "Admin employee is not linked "
                "to the initial admin user."
            )

        print("Initial data check passed.")
        print(f"Company: {company.code} - {company.name}")
        print("Roles: " + ", ".join(SYSTEM_ROLES))
        print(f"Admin username: {admin_user.username}")
        print(
            "Admin employee number: "
            f"{admin_employee.employee_number}"
        )
        print(
            "Must change password: "
            f"{admin_user.must_change_password}"
        )


if __name__ == "__main__":
    main()
