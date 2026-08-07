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

            if "logo_filename" not in company_columns:
                connection.execute(
                    text(
                        "ALTER TABLE companies "
                        "ADD COLUMN logo_filename VARCHAR(255)"
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
        employee_columns = {
            column["name"]
            for column in inspector.get_columns("employees")
        }

        with engine.begin() as connection:
            if "telephone_mobile_no" not in employee_columns:
                connection.execute(
                    text(
                        "ALTER TABLE employees "
                        "ADD COLUMN telephone_mobile_no VARCHAR(50)"
                    )
                )


            if "leader_id" not in employee_columns:
                connection.execute(
                    text(
                        "ALTER TABLE employees "
                        "ADD COLUMN leader_id INTEGER"
                    )
                )

            if "gender" not in employee_columns:
                connection.execute(
                    text(
                        "ALTER TABLE employees "
                        "ADD COLUMN gender VARCHAR(50)"
                    )
                )

            if "civil_status" not in employee_columns:
                connection.execute(
                    text(
                        "ALTER TABLE employees "
                        "ADD COLUMN civil_status VARCHAR(50)"
                    )
                )

            if "date_of_birth" not in employee_columns:
                connection.execute(
                    text(
                        "ALTER TABLE employees "
                        "ADD COLUMN date_of_birth DATE"
                    )
                )

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


    # Smart reminder milestones and recoverable Reminder Bin.
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    if "event_reminders" in table_names:
        reminder_columns = {
            column["name"]
            for column in inspector.get_columns("event_reminders")
        }
        datetime_sql = (
            "TIMESTAMP WITH TIME ZONE"
            if engine.dialect.name == "postgresql"
            else "DATETIME"
        )

        with engine.begin() as connection:
            for column_name in (
                "reminder_one_month_sent_at",
                "reminder_two_weeks_sent_at",
                "reminder_one_week_sent_at",
                "archived_at",
            ):
                if column_name not in reminder_columns:
                    connection.execute(
                        text(
                            "ALTER TABLE event_reminders "
                            f"ADD COLUMN {column_name} {datetime_sql}"
                        )
                    )

            if "archived_by_user_id" not in reminder_columns:
                connection.execute(
                    text(
                        "ALTER TABLE event_reminders "
                        "ADD COLUMN archived_by_user_id INTEGER"
                    )
                )

            # A legacy reminder already marked sent must not generate three
            # duplicate catch-up notifications after this upgrade.
            connection.execute(
                text(
                    """
                    UPDATE event_reminders
                    SET reminder_one_month_sent_at = reminder_sent_at,
                        reminder_two_weeks_sent_at = reminder_sent_at,
                        reminder_one_week_sent_at = reminder_sent_at
                    WHERE reminder_sent_at IS NOT NULL
                    """
                )
            )


    # Preserve reminders created in the short-lived announcement-bound design.
    # The new architecture stores planning reminders independently, while an
    # optional announcement link remains available after the post is prepared.
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    if "announcements" in table_names and "event_reminders" in table_names:
        announcement_columns = {
            column["name"]
            for column in inspector.get_columns("announcements")
        }
        legacy_columns = {
            "event_start_at",
            "event_end_at",
            "reminder_enabled",
            "reminder_lead_minutes",
            "reminder_at",
            "reminder_sent_at",
        }

        if legacy_columns.issubset(announcement_columns):
            with engine.begin() as connection:
                legacy_rows = connection.execute(
                    text(
                        """
                        SELECT
                            id, company_id, created_by_user_id,
                            updated_by_user_id, title, category, summary,
                            event_start_at, event_end_at,
                            reminder_lead_minutes, reminder_at,
                            reminder_sent_at
                        FROM announcements
                        WHERE reminder_enabled = 1
                          AND event_start_at IS NOT NULL
                          AND reminder_at IS NOT NULL
                        """
                    )
                ).mappings().all()

                for row in legacy_rows:
                    existing = connection.execute(
                        text(
                            "SELECT id FROM event_reminders "
                            "WHERE announcement_id = :announcement_id"
                        ),
                        {"announcement_id": int(row["id"])},
                    ).first()

                    if existing is not None:
                        continue

                    connection.execute(
                        text(
                            """
                            INSERT INTO event_reminders (
                                public_id, company_id, created_by_user_id,
                                updated_by_user_id, title, category, notes,
                                event_start_at, event_end_at,
                                reminder_lead_minutes, reminder_at,
                                reminder_sent_at, status, announcement_id
                            ) VALUES (
                                :public_id, :company_id, :created_by_user_id,
                                :updated_by_user_id, :title, :category, :notes,
                                :event_start_at, :event_end_at,
                                :reminder_lead_minutes, :reminder_at,
                                :reminder_sent_at, 'announcement_ready',
                                :announcement_id
                            )
                            """
                        ),
                        {
                            "public_id": f"REM_MIG_{int(row['id']):06d}",
                            "company_id": int(row["company_id"]),
                            "created_by_user_id": int(row["created_by_user_id"]),
                            "updated_by_user_id": int(row["updated_by_user_id"]),
                            "title": str(row["title"]),
                            "category": "Company Event",
                            "notes": str(row["summary"] or ""),
                            "event_start_at": row["event_start_at"],
                            "event_end_at": row["event_end_at"],
                            "reminder_lead_minutes": int(
                                row["reminder_lead_minutes"] or 10080
                            ),
                            "reminder_at": row["reminder_at"],
                            "reminder_sent_at": row["reminder_sent_at"],
                            "announcement_id": int(row["id"]),
                        },
                    )


    # Phase 1 leave-credit ledger columns. Existing records are retained and
    # mapped to the clearer Beginning Credit / Credit / Converted to Cash
    # structure only when the new columns are first introduced.
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    if "leave_balances" in table_names:
        balance_columns = {
            column["name"]
            for column in inspector.get_columns("leave_balances")
        }
        phase_one_columns_added = False

        with engine.begin() as connection:
            for column_name in (
                "beginning_credit_days",
                "credit_days",
                "converted_to_cash_days",
            ):
                if column_name not in balance_columns:
                    connection.execute(
                        text(
                            "ALTER TABLE leave_balances "
                            f"ADD COLUMN {column_name} "
                            "NUMERIC(8, 2) NOT NULL DEFAULT 0.00"
                        )
                    )
                    phase_one_columns_added = True

            if phase_one_columns_added:
                # Preserve the numeric meaning of every older balance:
                # carry-over becomes Beginning Credit, automatic allocation
                # becomes Credit, and the existing adjustment column remains
                # the separate administrator correction bucket.
                connection.execute(
                    text(
                        "UPDATE leave_balances "
                        "SET beginning_credit_days = "
                        "COALESCE(carry_over_days, 0), "
                        "credit_days = "
                        "COALESCE(allocated_days, 0), "
                        "converted_to_cash_days = "
                        "COALESCE(converted_to_cash_days, 0)"
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
        paid_true_sql = (
            "TRUE"
            if engine.dialect.name == "postgresql"
            else "1"
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
                (
                    "fallback_leave_type_id",
                    "INTEGER",
                ),
                (
                    "primary_credit_days",
                    "NUMERIC(8, 2) NOT NULL DEFAULT 0",
                ),
                (
                    "fallback_credit_days",
                    "NUMERIC(8, 2) NOT NULL DEFAULT 0",
                ),
                (
                    "lwop_days",
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

            # Existing requests predate the paid-credit/LWOP split. Preserve
            # their previous behavior by assigning all paid requests to the
            # primary leave type and all non-paid requests to LWOP.
            connection.execute(
                text(
                    f"""
                    UPDATE leave_requests
                    SET primary_credit_days = CASE
                            WHEN leave_type_id IN (
                                SELECT id FROM leave_types
                                WHERE is_paid = {paid_true_sql}
                                  AND annual_credits > 0
                            )
                            THEN requested_days ELSE 0 END,
                        fallback_credit_days = 0,
                        lwop_days = CASE
                            WHEN leave_type_id IN (
                                SELECT id FROM leave_types
                                WHERE is_paid = {paid_true_sql}
                                  AND annual_credits > 0
                            )
                            THEN 0 ELSE requested_days END
                    WHERE COALESCE(primary_credit_days, 0) = 0
                      AND COALESCE(fallback_credit_days, 0) = 0
                      AND COALESCE(lwop_days, 0) = 0
                    """
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
