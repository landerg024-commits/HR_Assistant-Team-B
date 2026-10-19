"""Safe additive migration for the ``auth_sessions`` table.

Why this module exists:
SQLAlchemy ``create_all()`` creates missing tables, but it does not add a
new column to a table that already exists. Older project versions may
therefore have an ``auth_sessions`` table without ``last_used_at``.

This migration:
- Preserves the existing database and all account records.
- Adds only known additive timestamp columns when missing.
- Backfills required timestamp values for old session rows.
- Is idempotent and safe to run repeatedly.
- Supports SQLite development and PostgreSQL production.

It intentionally refuses to invent missing identity/security columns such
as company_id, user_id, token_hash, or expires_at.
"""

from datetime import datetime, timezone

from sqlalchemy import Engine, inspect, text


AUTH_SESSION_TABLE = "auth_sessions"

# Missing identity/security columns indicate an incompatible table rather
# than a simple additive upgrade. Those cases require a reviewed migration.
CRITICAL_COLUMNS = {
    "id",
    "company_id",
    "user_id",
    "token_hash",
    "expires_at",
}

# These fields may be added safely to an existing compatible table.
ADDITIVE_TIMESTAMP_COLUMNS = (
    "last_used_at",
    "revoked_at",
    "created_at",
    "updated_at",
)

# Required timestamp fields are backfilled after they are added.
REQUIRED_TIMESTAMP_COLUMNS = {
    "last_used_at",
    "created_at",
    "updated_at",
}


def _timestamp_sql_type(dialect_name: str) -> str:
    """Return a compatible timestamp type for the selected database."""

    if dialect_name == "postgresql":
        return "TIMESTAMP WITH TIME ZONE"

    # SQLite stores SQLAlchemy DateTime values safely using DATETIME.
    return "DATETIME"


def migrate_auth_sessions_schema(
    engine: Engine,
) -> list[str]:
    """Add missing compatible columns and return their names.

    When the table does not exist, no migration is needed because
    ``Base.metadata.create_all()`` is responsible for creating it.
    """

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    if AUTH_SESSION_TABLE not in table_names:
        return []

    existing_columns = {
        column["name"]
        for column in inspector.get_columns(AUTH_SESSION_TABLE)
    }

    missing_critical = CRITICAL_COLUMNS - existing_columns

    if missing_critical:
        raise RuntimeError(
            "The existing auth_sessions table is incompatible. "
            "Missing critical columns: "
            + ", ".join(sorted(missing_critical))
        )

    missing_additive = [
        column_name
        for column_name in ADDITIVE_TIMESTAMP_COLUMNS
        if column_name not in existing_columns
    ]

    if not missing_additive:
        return []

    timestamp_type = _timestamp_sql_type(
        engine.dialect.name
    )
    now = datetime.now(timezone.utc)

    with engine.begin() as connection:
        for column_name in missing_additive:
            # Column names come only from the fixed constant above and are
            # never based on user input.
            connection.execute(
                text(
                    f"ALTER TABLE {AUTH_SESSION_TABLE} "
                    f"ADD COLUMN {column_name} {timestamp_type}"
                )
            )

        # Old rows need values for fields used as required model values.
        for column_name in (
            REQUIRED_TIMESTAMP_COLUMNS
            & set(missing_additive)
        ):
            connection.execute(
                text(
                    f"UPDATE {AUTH_SESSION_TABLE} "
                    f"SET {column_name} = :timestamp "
                    f"WHERE {column_name} IS NULL"
                ),
                {"timestamp": now},
            )

        # PostgreSQL can enforce NOT NULL after the backfill. SQLite cannot
        # change nullability with a simple ALTER COLUMN, but all old rows are
        # backfilled and all new ORM writes provide these values.
        if engine.dialect.name == "postgresql":
            for column_name in (
                REQUIRED_TIMESTAMP_COLUMNS
                & set(missing_additive)
            ):
                connection.execute(
                    text(
                        f"ALTER TABLE {AUTH_SESSION_TABLE} "
                        f"ALTER COLUMN {column_name} SET NOT NULL"
                    )
                )

    return missing_additive
