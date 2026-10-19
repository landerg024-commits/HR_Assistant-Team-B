"""Create the configured database tables.

Run directly from the project root:

    python scripts\\create_database.py

Or run as a module:

    python -m scripts.create_database
"""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from config.settings import get_settings
from database.connection_manager import DatabaseConnectionManager


def main() -> None:
    """Test the connection and create all registered tables."""

    settings = get_settings()
    manager = DatabaseConnectionManager()

    manager.test_connection()
    manager.create_tables()

    print("Database connection successful.")
    print("Database tables created successfully.")
    print(f"Database URL: {settings.database_url}")


if __name__ == "__main__":
    main()
