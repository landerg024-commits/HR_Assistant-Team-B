"""Check whether the default administrator must change its password.

Run:

    python scripts/check_default_password_reset.py
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
    """Print the configured default administrator reset status."""

    settings = get_settings()

    with SessionFactory() as session:
        company = CompanyRepository(session).get_by_code(
            settings.initial_company_code
        )

        if company is None:
            raise RuntimeError("Default company was not found.")

        admin_user = UserRepository(session).get_by_username(
            company.id,
            settings.initial_admin_username,
        )

        if admin_user is None:
            raise RuntimeError(
                "Default administrator was not found."
            )

        print("Default administrator password-reset check")
        print(f"Company code: {company.code}")
        print(f"Username: {admin_user.username}")
        print(
            "Must change password: "
            f"{admin_user.must_change_password}"
        )


if __name__ == "__main__":
    main()
