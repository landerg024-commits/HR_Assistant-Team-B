"""Default SQLAlchemy database adapter.

This adapter already supports SQLite, PostgreSQL, and other SQLAlchemy
connection URLs without changing repositories or business services.
"""

from sqlalchemy import text
from sqlalchemy.engine import Engine

from database.adapters.base_adapter import BaseDatabaseAdapter
from database.session import create_database_engine


class SQLAlchemyDatabaseAdapter(BaseDatabaseAdapter):
    """Concrete adapter that uses SQLAlchemy."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._engine: Engine | None = None

    def create_engine(self) -> Engine:
        """Create the engine once, then reuse it."""

        if self._engine is None:
            self._engine = create_database_engine(self.database_url)

        return self._engine

    def test_connection(self) -> bool:
        """Run a small query to verify the connection."""

        with self.create_engine().connect() as connection:
            connection.execute(text("SELECT 1"))

        return True
