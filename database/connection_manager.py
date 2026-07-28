"""Database health-check and schema initialization helpers."""

from sqlalchemy import text
from sqlalchemy.engine import Engine

from database.base import Base
from database.schema_upgrade import upgrade_existing_schema
from database.session import engine


class DatabaseConnectionManager:
    """Coordinate low-level database connection tasks."""

    def __init__(self, selected_engine: Engine | None = None) -> None:
        # A custom engine is accepted to support isolated tests.
        self.engine = selected_engine or engine

    def test_connection(self) -> bool:
        """Execute a minimal query to confirm the database is reachable."""

        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return True

    def create_tables(self) -> None:
        """Create all tables registered in SQLAlchemy metadata."""

        # Model imports register each table in Base.metadata.
        # Without this import, create_all() may not see the model classes.
        import models  # noqa: F401

        Base.metadata.create_all(bind=self.engine)
        upgrade_existing_schema(self.engine)
