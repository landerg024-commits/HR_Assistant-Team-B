"""Verify persistent login storage against the configured database.

Run from the project root:

    python scripts/check_persistent_login.py

The script does not change passwords or create user accounts. It creates
missing registered tables, verifies the ``auth_sessions`` table, and prints
the configured session duration.
"""

from pathlib import Path
import sys

from sqlalchemy import inspect


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from config.settings import get_settings
from database.runtime_schema import initialize_runtime_schema
from database.session import engine


def main() -> None:
    """Initialize and verify the persistent authentication schema."""

    initialize_runtime_schema()

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    if "auth_sessions" not in table_names:
        raise RuntimeError(
            "The auth_sessions table was not created."
        )

    required_columns = {
        "id",
        "company_id",
        "user_id",
        "token_hash",
        "expires_at",
        "last_used_at",
        "revoked_at",
        "created_at",
        "updated_at",
    }

    actual_columns = {
        column["name"]
        for column in inspector.get_columns("auth_sessions")
    }

    missing_columns = required_columns - actual_columns

    if missing_columns:
        raise RuntimeError(
            "auth_sessions is missing columns: "
            + ", ".join(sorted(missing_columns))
            + ". Run: python scripts/migrate_auth_sessions.py"
        )

    settings = get_settings()

    print("Persistent login database check passed.")
    print("Table: auth_sessions")
    print(f"Session duration: {settings.auth_session_hours} hour(s)")
    print(f"Database URL: {settings.database_url}")


if __name__ == "__main__":
    main()
