"""Check the sample employee-only account and permissions.

Run:

    python scripts/check_sample_employee_account.py
"""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from authentication.access_control import AccessControl
from authentication.current_user import AuthenticatedUser
from config.settings import get_settings
from database.session import SessionFactory
from repositories.company_repository import CompanyRepository
from repositories.user_repository import UserRepository


SAMPLE_USERNAME = "employee.test"


def main() -> None:
    """Print employee role and portal-access expectations."""

    settings = get_settings()

    with SessionFactory() as session:
        company = CompanyRepository(session).get_by_code(
            settings.initial_company_code
        )

        if company is None:
            raise RuntimeError("Configured company was not found.")

        user = UserRepository(session).get_for_authentication(
            company_id=company.id,
            login_identifier=SAMPLE_USERNAME,
        )

        if user is None:
            raise RuntimeError(
                "Sample employee account was not found. "
                "Run: python scripts/create_sample_employee_account.py"
            )

        current_user = AuthenticatedUser.from_model(user)

        print("Sample employee account check")
        print(f"Company code: {current_user.company_code}")
        print(f"Username: {current_user.username}")
        print(f"Role: {current_user.role_name}")
        print(
            "Employee portal access: "
            f"{AccessControl.can_access_employee_portal(current_user)}"
        )
        print(
            "Administrator access: "
            f"{AccessControl.is_admin(current_user)}"
        )
        print(
            "Must change password: "
            f"{current_user.must_change_password}"
        )

        if AccessControl.is_admin(current_user):
            raise RuntimeError(
                "Employee-only account unexpectedly has admin access."
            )

        print("Employee-only access check passed.")


if __name__ == "__main__":
    main()
