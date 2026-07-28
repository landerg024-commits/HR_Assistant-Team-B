"""Require the configured default administrator to change its password.

Run from the project root:

    python scripts/require_default_password_reset.py

What it changes:
- Sets ``must_change_password=True`` for the configured initial admin.
- Does not change or reveal the current password.
- Does not delete users, employees, companies, or other records.

After running this script, the default administrator can sign in using its
current password. The app will redirect directly to the mandatory password
change page before allowing access to protected portals.
"""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from config.settings import get_settings
from database.session import SessionFactory
from repositories.company_repository import CompanyRepository
from repositories.user_repository import UserRepository


def main() -> None:
    """Enable mandatory password replacement for the default admin."""

    settings = get_settings()

    with SessionFactory() as session:
        company = CompanyRepository(session).get_by_code(
            settings.initial_company_code
        )

        if company is None:
            raise RuntimeError(
                "The configured default company was not found. "
                "Run: python scripts/create_initial_data.py"
            )

        admin_user = UserRepository(session).get_by_username(
            company.id,
            settings.initial_admin_username,
        )

        if admin_user is None:
            raise RuntimeError(
                "The configured default administrator was not found. "
                "Run: python scripts/create_initial_data.py"
            )

        admin_user.must_change_password = True
        session.commit()
        session.refresh(admin_user)

        print("Default administrator password reset is now required.")
        print(f"Company code: {company.code}")
        print(f"Username: {admin_user.username}")
        print(
            "Must change password: "
            f"{admin_user.must_change_password}"
        )
        print(
            "Sign in using the account's current password. "
            "The app will open the password change page."
        )


if __name__ == "__main__":
    main()
