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



    # Leave approval and date-based credit posting.
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    if "leave_types" in table_names:
        leave_type_columns = {
            column["name"]
            for column in inspector.get_columns("leave_types")
        }

        with engine.begin() as connection:
            if (
                "handover_plan_requirement"
                not in leave_type_columns
            ):
                connection.execute(
                    text(
                        "ALTER TABLE leave_types "
                        "ADD COLUMN handover_plan_requirement "
                        "VARCHAR(20) NOT NULL DEFAULT 'optional'"
                    )
                )
                connection.execute(
                    text(
                        "UPDATE leave_types "
                        "SET handover_plan_requirement = "
                        "CASE "
                        "WHEN upper(code) IN ('VACATION', 'LWOP') "
                        "THEN 'recommended' "
                        "ELSE 'optional' END"
                    )
                )

    if "leave_requests" in table_names:
        request_columns = {
            column["name"]
            for column in inspector.get_columns("leave_requests")
        }
        datetime_sql = (
            "TIMESTAMP WITH TIME ZONE"
            if engine.dialect.name == "postgresql"
            else "DATETIME"
        )
        boolean_sql = (
            "BOOLEAN NOT NULL DEFAULT FALSE"
            if engine.dialect.name == "postgresql"
            else "BOOLEAN NOT NULL DEFAULT 0"
        )
        added_reservation_tracking = (
            "reservation_posted" not in request_columns
        )

        with engine.begin() as connection:
            additions = (
                (
                    "handover_plan",
                    "TEXT",
                ),
                (
                    "manager_comment",
                    "TEXT",
                ),
                (
                    "reviewed_at",
                    datetime_sql,
                ),
                (
                    "reviewed_by_user_id",
                    "INTEGER",
                ),
                (
                    "approved_at",
                    datetime_sql,
                ),
                (
                    "completed_at",
                    datetime_sql,
                ),
                (
                    "reservation_posted",
                    boolean_sql,
                ),
                (
                    "posted_working_days",
                    "NUMERIC(8, 2) NOT NULL DEFAULT 0",
                ),
            )

            for column_name, column_sql in additions:
                if column_name not in request_columns:
                    connection.execute(
                        text(
                            "ALTER TABLE leave_requests "
                            f"ADD COLUMN {column_name} "
                            f"{column_sql}"
                        )
                    )

            # v8.5.x reserved credits immediately on submission. When this
            # tracking field is first introduced, release those pending
            # reservations and convert the request to the new workflow.
            if added_reservation_tracking:
                legacy_rows = connection.execute(
                    text(
                        "SELECT id, company_id, employee_id, "
                        "leave_type_id, start_date, requested_days "
                        "FROM leave_requests "
                        "WHERE status = 'sent_to_manager'"
                    )
                ).mappings().all()

                for row in legacy_rows:
                    start_year = int(
                        str(row["start_date"])[:4]
                    )
                    connection.execute(
                        text(
                            "UPDATE leave_balances "
                            "SET reserved_days = CASE "
                            "WHEN reserved_days >= :days "
                            "THEN reserved_days - :days "
                            "ELSE 0 END "
                            "WHERE company_id = :company_id "
                            "AND employee_id = :employee_id "
                            "AND leave_type_id = :leave_type_id "
                            "AND year = :year"
                        ),
                        {
                            "days": row["requested_days"],
                            "company_id": row["company_id"],
                            "employee_id": row["employee_id"],
                            "leave_type_id": row["leave_type_id"],
                            "year": start_year,
                        },
                    )

                connection.execute(
                    text(
                        "UPDATE leave_requests "
                        "SET status = 'pending_manager_approval', "
                        "reservation_posted = "
                        + (
                            "FALSE"
                            if engine.dialect.name == "postgresql"
                            else "0"
                        )
                        + ", posted_working_days = 0 "
                        "WHERE status = 'sent_to_manager'"
                    )
                )
