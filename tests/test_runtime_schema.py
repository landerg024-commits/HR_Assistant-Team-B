"""Tests for runtime database schema initialization."""

from sqlalchemy import create_engine, inspect

import models  # noqa: F401
from database.base import Base


def test_create_all_adds_auth_sessions_to_existing_schema() -> None:
    """An upgraded database receives the missing auth session table."""

    engine = create_engine("sqlite+pysqlite:///:memory:")

    # Simulate an older installation with the original core tables only.
    original_tables = [
        models.Company.__table__,
        models.Role.__table__,
        models.User.__table__,
        models.Department.__table__,
        models.Employee.__table__,
    ]

    for table in original_tables:
        table.create(bind=engine, checkfirst=True)

    assert (
        "auth_sessions"
        not in inspect(engine).get_table_names()
    )

    Base.metadata.create_all(bind=engine)

    assert (
        "auth_sessions"
        in inspect(engine).get_table_names()
    )


def test_create_all_preserves_existing_tables() -> None:
    """Repeated initialization is safe and idempotent."""

    engine = create_engine("sqlite+pysqlite:///:memory:")

    Base.metadata.create_all(bind=engine)
    first_tables = set(inspect(engine).get_table_names())

    Base.metadata.create_all(bind=engine)
    second_tables = set(inspect(engine).get_table_names())

    assert first_tables == second_tables
    assert "users" in second_tables
    assert "auth_sessions" in second_tables
