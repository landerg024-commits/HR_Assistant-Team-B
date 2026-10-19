"""Tests for additive authentication-session schema migration."""

from sqlalchemy import create_engine, inspect, text

from database.auth_session_migration import (
    migrate_auth_sessions_schema,
)


def _create_old_compatible_schema(engine) -> None:
    """Create a simplified older table missing last_used_at."""

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE auth_sessions (
                    id INTEGER PRIMARY KEY,
                    company_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    token_hash VARCHAR(64) NOT NULL,
                    expires_at DATETIME NOT NULL,
                    revoked_at DATETIME,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )

        connection.execute(
            text(
                """
                INSERT INTO auth_sessions (
                    id,
                    company_id,
                    user_id,
                    token_hash,
                    expires_at,
                    revoked_at,
                    created_at,
                    updated_at
                )
                VALUES (
                    1,
                    1,
                    1,
                    :token_hash,
                    :expires_at,
                    NULL,
                    :created_at,
                    :updated_at
                )
                """
            ),
            {
                "token_hash": "a" * 64,
                "expires_at": "2030-01-01 00:00:00",
                "created_at": "2026-01-01 00:00:00",
                "updated_at": "2026-01-01 00:00:00",
            },
        )


def test_migration_adds_and_backfills_last_used_at() -> None:
    """The reported user's old table should upgrade without data loss."""

    engine = create_engine("sqlite+pysqlite:///:memory:")
    _create_old_compatible_schema(engine)

    added = migrate_auth_sessions_schema(engine)

    assert "last_used_at" in added

    columns = {
        column["name"]
        for column in inspect(engine).get_columns(
            "auth_sessions"
        )
    }
    assert "last_used_at" in columns

    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT token_hash, last_used_at
                FROM auth_sessions
                WHERE id = 1
                """
            )
        ).mappings().one()

    assert row["token_hash"] == "a" * 64
    assert row["last_used_at"] is not None


def test_migration_is_idempotent() -> None:
    """Running the migration repeatedly must not add duplicates."""

    engine = create_engine("sqlite+pysqlite:///:memory:")
    _create_old_compatible_schema(engine)

    first_added = migrate_auth_sessions_schema(engine)
    second_added = migrate_auth_sessions_schema(engine)

    assert "last_used_at" in first_added
    assert second_added == []


def test_incompatible_table_is_rejected() -> None:
    """Missing security identity fields must not be invented silently."""

    engine = create_engine("sqlite+pysqlite:///:memory:")

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE auth_sessions (
                    id INTEGER PRIMARY KEY
                )
                """
            )
        )

    try:
        migrate_auth_sessions_schema(engine)
    except RuntimeError as error:
        assert "Missing critical columns" in str(error)
    else:
        raise AssertionError(
            "An incompatible auth_sessions table was accepted."
        )
