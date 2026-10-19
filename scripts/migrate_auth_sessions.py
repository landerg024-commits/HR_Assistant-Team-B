"""Upgrade an existing ``auth_sessions`` table safely.

Run from the project root:

    python scripts/migrate_auth_sessions.py

This script preserves the existing database. It does not delete users,
passwords, employees, companies, or existing authentication sessions.
"""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from database.auth_session_migration import (
    migrate_auth_sessions_schema,
)
from database.base import Base
from database.session import engine


def main() -> None:
    """Create a missing table or upgrade a compatible existing table."""

    # Register every model before create_all().
    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    added_columns = migrate_auth_sessions_schema(engine)

    if added_columns:
        print("Authentication session migration completed.")
        print(
            "Added columns: "
            + ", ".join(added_columns)
        )
    else:
        print(
            "Authentication session schema is already up to date."
        )

    print("Existing database records were preserved.")


if __name__ == "__main__":
    main()
