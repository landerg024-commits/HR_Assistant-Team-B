"""Safely clear leave test data without deleting employees or leave types.

Purpose:
- Remove leave requests, leave-credit transactions, and leave balances.
- Remove in-app notifications linked to deleted leave requests.
- Delete stored leave-request attachments after the database commit.
- Recreate clean current-year leave balances from configured leave types.
- Back up the SQLite database before making changes.

Run from the project root after stopping Streamlit:
    python -m scripts.reset_leave_test_data --confirm

The default company comes from INITIAL_COMPANY_CODE. Use --company-code for a
specific tenant or --all-companies to reset every company in the database.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sqlite3

from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from config.settings import Settings, get_settings
from database.runtime_schema import initialize_runtime_schema
from database.session import SessionFactory
from models.company import Company
from models.leave_balance import LeaveBalance
from models.leave_credit_transaction import LeaveCreditTransaction
from models.leave_request import LeaveRequest
from models.notification import Notification
from modules.leave.leave_file_storage import LeaveFileStorage
from services.leave_service import LeaveService


@dataclass(frozen=True, slots=True)
class LeaveResetResult:
    """Counts returned after resetting one company's leave data."""

    company_id: int
    company_code: str
    requests_deleted: int
    balances_deleted: int
    transactions_deleted: int
    notifications_deleted: int
    attachments_deleted: int


def _row_count(result) -> int:
    """Return a safe non-negative row count for SQLAlchemy delete results."""

    value = result.rowcount
    return max(int(value or 0), 0)


def _sqlite_database_path(settings: Settings) -> Path | None:
    """Resolve the configured SQLite database path, if one is in use."""

    url = make_url(settings.database_url)
    if not url.drivername.startswith("sqlite"):
        return None
    if not url.database or url.database == ":memory:":
        return None

    database_path = Path(url.database)
    if not database_path.is_absolute():
        database_path = Path.cwd() / database_path
    return database_path.resolve()


def backup_sqlite_database(settings: Settings) -> Path | None:
    """Create a consistent SQLite backup before destructive cleanup."""

    database_path = _sqlite_database_path(settings)
    if database_path is None or not database_path.exists():
        return None

    backup_dir = database_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"hr_assistant_before_leave_reset_{timestamp}.db"

    # sqlite3.backup creates a consistent copy even when SQLite uses WAL mode.
    with sqlite3.connect(database_path) as source:
        with sqlite3.connect(backup_path) as destination:
            source.backup(destination)

    return backup_path


def reset_company_leave_data(
    session: Session,
    *,
    company: Company,
    settings: Settings,
    recreate_current_year: bool = True,
) -> LeaveResetResult:
    """Reset leave-only records for one company and preserve all HR master data."""

    request_rows = session.execute(
        select(
            LeaveRequest.id,
            LeaveRequest.attachment_storage_path,
        ).where(LeaveRequest.company_id == company.id)
    ).all()
    attachment_paths = [
        str(row.attachment_storage_path)
        for row in request_rows
        if row.attachment_storage_path
    ]

    # Remove dependent audit rows before their parent balances and requests.
    transactions_deleted = _row_count(
        session.execute(
            delete(LeaveCreditTransaction).where(
                LeaveCreditTransaction.company_id == company.id
            )
        )
    )

    notifications_deleted = _row_count(
        session.execute(
            delete(Notification).where(
                Notification.company_id == company.id,
                Notification.related_entity_type == "leave_request",
            )
        )
    )
    requests_deleted = _row_count(
        session.execute(
            delete(LeaveRequest).where(LeaveRequest.company_id == company.id)
        )
    )
    balances_deleted = _row_count(
        session.execute(
            delete(LeaveBalance).where(LeaveBalance.company_id == company.id)
        )
    )

    session.commit()

    # Delete only attachment paths already validated by LeaveFileStorage.
    storage = LeaveFileStorage(settings.leave_attachment_dir)
    attachments_deleted = 0
    for storage_path in attachment_paths:
        full_path = (storage.root_dir / storage_path).resolve()
        existed = full_path.is_file()
        storage.delete(storage_path)
        if existed and not full_path.exists():
            attachments_deleted += 1

    if recreate_current_year:
        # Rebuild clean current-year balances using the configured leave types.
        LeaveService(session, settings=settings).ensure_current_year_balances(
            company.id
        )

    return LeaveResetResult(
        company_id=company.id,
        company_code=company.code,
        requests_deleted=requests_deleted,
        balances_deleted=balances_deleted,
        transactions_deleted=transactions_deleted,
        notifications_deleted=notifications_deleted,
        attachments_deleted=attachments_deleted,
    )


def _selected_companies(
    session: Session,
    *,
    company_code: str,
    all_companies: bool,
) -> list[Company]:
    """Return the exact companies requested by the command-line arguments."""

    if all_companies:
        return list(session.scalars(select(Company).order_by(Company.id)).all())

    normalized_code = company_code.strip().upper()
    company = session.scalar(
        select(Company).where(Company.code == normalized_code)
    )
    if company is None:
        raise ValueError(f"Company code '{normalized_code}' was not found.")
    return [company]


def main() -> None:
    """Back up SQLite and reset the selected company's leave test records."""

    parser = argparse.ArgumentParser(
        description=(
            "Clear leave requests, balances, credit history, linked "
            "notifications, and leave attachments while preserving employees."
        )
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required confirmation for the destructive leave-only reset.",
    )
    parser.add_argument(
        "--company-code",
        help="Company code to reset; defaults to INITIAL_COMPANY_CODE.",
    )
    parser.add_argument(
        "--all-companies",
        action="store_true",
        help="Reset leave data for every company.",
    )
    parser.add_argument(
        "--no-recreate-balances",
        action="store_true",
        help="Leave the balance table empty instead of rebuilding this year.",
    )
    args = parser.parse_args()

    if not args.confirm:
        parser.error(
            "Reset cancelled. Re-run with --confirm after stopping Streamlit."
        )

    settings = get_settings()
    initialize_runtime_schema()

    backup_path = backup_sqlite_database(settings)
    if backup_path is not None:
        print(f"SQLite backup created: {backup_path}")
    elif settings.database_url.startswith("sqlite"):
        print("SQLite database file was not found; continuing without a backup.")
    else:
        print(
            "Non-SQLite database detected. Create an external database backup "
            "before using this command in production."
        )

    selected_code = args.company_code or settings.initial_company_code

    with SessionFactory() as session:
        companies = _selected_companies(
            session,
            company_code=selected_code,
            all_companies=args.all_companies,
        )

        results = [
            reset_company_leave_data(
                session,
                company=company,
                settings=settings,
                recreate_current_year=not args.no_recreate_balances,
            )
            for company in companies
        ]

    print("Leave test-data reset completed.")
    for result in results:
        print(
            f"[{result.company_code}] requests={result.requests_deleted}, "
            f"balances={result.balances_deleted}, "
            f"transactions={result.transactions_deleted}, "
            f"notifications={result.notifications_deleted}, "
            f"attachments={result.attachments_deleted}"
        )
    print("Employees, users, companies, departments, and leave types were preserved.")


if __name__ == "__main__":
    main()
