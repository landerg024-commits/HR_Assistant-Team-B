"""Non-destructive upgrades for databases created by earlier checkpoints."""

from sqlalchemy import Engine, inspect, text


def upgrade_existing_schema(engine: Engine) -> None:
    """Add new columns and normalize legacy values without deleting data."""

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    if "companies" in table_names:
        company_columns = {
            column["name"]
            for column in inspector.get_columns("companies")
        }

        with engine.begin() as connection:
            if "theme_primary_color" not in company_columns:
                connection.execute(
                    text(
                        "ALTER TABLE companies "
                        "ADD COLUMN theme_primary_color "
                        "VARCHAR(7) NOT NULL DEFAULT '#4338E8'"
                    )
                )

            connection.execute(
                text(
                    "UPDATE companies "
                    "SET theme_primary_color = '#4338E8' "
                    "WHERE theme_primary_color IS NULL "
                    "OR trim(theme_primary_color) = ''"
                )
            )

    if "users" in table_names:
        user_columns = {
            column["name"]
            for column in inspector.get_columns("users")
        }

        if "clearance" not in user_columns:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE users "
                        "ADD COLUMN clearance INTEGER NOT NULL DEFAULT 2"
                    )
                )

                # Convert existing administrator roles to clearance 1.
                # All remaining roles become the standard user clearance.
                if "roles" in table_names:
                    connection.execute(
                        text(
                            """
                            UPDATE users
                            SET clearance = CASE
                                WHEN role_id IN (
                                    SELECT id
                                    FROM roles
                                    WHERE name IN (
                                        'super_admin',
                                        'company_admin',
                                        'hr_admin'
                                    )
                                )
                                THEN 1
                                ELSE 2
                            END
                            """
                        )
                    )

    if "employees" in table_names:
        with engine.begin() as connection:
            # Earlier versions stored active/inactive. Preserve the records
            # while converting them to the new user-facing terms.
            connection.execute(
                text(
                    """
                    UPDATE employees
                    SET employment_status = 'employed'
                    WHERE lower(employment_status) IN (
                        'active',
                        'employed'
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    UPDATE employees
                    SET employment_status = 'resigned'
                    WHERE lower(employment_status) IN (
                        'inactive',
                        'resigned',
                        'terminated'
                    )
                    """
                )
            )
    if "hr_policies" in table_names:
        policy_columns = {
            column["name"]
            for column in inspector.get_columns("hr_policies")
        }

        datetime_sql = (
            "TIMESTAMP WITH TIME ZONE"
            if engine.dialect.name == "postgresql"
            else "DATETIME"
        )

        with engine.begin() as connection:
            if "public_id" not in policy_columns:
                connection.execute(
                    text(
                        "ALTER TABLE hr_policies "
                        "ADD COLUMN public_id VARCHAR(30)"
                    )
                )

            if "trashed_at" not in policy_columns:
                connection.execute(
                    text(
                        "ALTER TABLE hr_policies "
                        f"ADD COLUMN trashed_at {datetime_sql}"
                    )
                )

            if "trashed_by_user_id" not in policy_columns:
                connection.execute(
                    text(
                        "ALTER TABLE hr_policies "
                        "ADD COLUMN trashed_by_user_id INTEGER"
                    )
                )

            rows = connection.execute(
                text(
                    "SELECT id FROM hr_policies "
                    "WHERE public_id IS NULL OR public_id = ''"
                )
            ).all()

            for row in rows:
                connection.execute(
                    text(
                        "UPDATE hr_policies "
                        "SET public_id = :public_id WHERE id = :id"
                    ),
                    {
                        "public_id": f"PID_{int(row.id):03d}",
                        "id": int(row.id),
                    },
                )

            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS "
                    "ux_hr_policies_public_id "
                    "ON hr_policies (public_id)"
                )
            )

