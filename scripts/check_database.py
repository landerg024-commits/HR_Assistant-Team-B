"""Check the configured database and list registered tables.

Run directly from the project root:

    python scripts\\check_database.py

Or run as a module:

    python -m scripts.check_database
"""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from sqlalchemy import inspect

from database.connection_manager import DatabaseConnectionManager


def main() -> None:
    """Verify database connectivity and required schema tables."""

    manager = DatabaseConnectionManager()
    manager.test_connection()

    inspector = inspect(manager.engine)
    table_names = sorted(inspector.get_table_names())

    expected_tables = {
        "companies",
        "roles",
        "departments",
        "users",
        "employees",
    }

    missing_tables = expected_tables.difference(table_names)

    if missing_tables:
        print("Missing tables:")

        for table_name in sorted(missing_tables):
            print(f" - {table_name}")

        raise SystemExit(1)

    print("Database architecture check passed.")
    print("Tables:")

    for table_name in table_names:
        print(f" - {table_name}")


if __name__ == "__main__":
    main()
