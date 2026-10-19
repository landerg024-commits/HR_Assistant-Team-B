r"""Verify persistent login, route, and theme tables.

Run:

    python scripts\check_persistent_sessions.py
"""

from pathlib import Path
import sys

from sqlalchemy import inspect


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from database.connection_manager import DatabaseConnectionManager


def main() -> None:
    """Create and verify all persistent-session tables."""

    manager = DatabaseConnectionManager()
    manager.test_connection()
    manager.create_tables()

    table_names = set(
        inspect(manager.engine).get_table_names()
    )

    required_tables = {
        "auth_sessions",
        "auth_session_navigation",
        "auth_session_preferences",
    }

    missing_tables = required_tables - table_names

    if missing_tables:
        raise SystemExit(
            "Missing persistent-session table(s): "
            + ", ".join(sorted(missing_tables))
        )

    print("Persistent session check passed.")
    print("Table: auth_sessions")
    print("Table: auth_session_navigation")
    print("Table: auth_session_preferences")


if __name__ == "__main__":
    main()
