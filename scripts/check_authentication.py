r"""Verify initial login credentials from `.env`.

Run this before changing the initial temporary password:

    python scripts\check_authentication.py

The script never prints the password or its hash.
"""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from authentication.auth_service import AuthService
from config.settings import get_settings
from database.session import SessionFactory


def main() -> None:
    """Authenticate the configured initial administrator."""

    settings = get_settings()

    with SessionFactory() as session:
        current_user = AuthService(session).authenticate(
            company_code=settings.initial_company_code,
            login_identifier=settings.initial_admin_username,
            password=(
                settings.initial_admin_password
                .get_secret_value()
            ),
        )

    print("Authentication check passed.")
    print(f"Company: {current_user.company_code}")
    print(f"Username: {current_user.username}")
    print(f"Role: {current_user.role_name}")
    print(
        "Must change password: "
        f"{current_user.must_change_password}"
    )


if __name__ == "__main__":
    main()
