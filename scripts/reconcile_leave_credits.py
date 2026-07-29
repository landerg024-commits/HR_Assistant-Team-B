"""Post elapsed approved leave days for every company.

This script is safe to run repeatedly because each leave request stores the
number of working days already posted. It can be scheduled once daily through
Windows Task Scheduler. The Streamlit app also runs the same reconciliation as
a safety fallback whenever an authenticated user opens the application.
"""

from sqlalchemy import select

from database.runtime_schema import initialize_runtime_schema
from database.session import SessionFactory
from models.company import Company
from services.leave_service import LeaveService


def main() -> None:
    """Reconcile every company and print the number of updated requests."""

    initialize_runtime_schema()

    with SessionFactory() as session:
        company_ids = list(
            session.scalars(
                select(Company.id)
            ).all()
        )

    total_changed = 0

    for company_id in company_ids:
        with SessionFactory() as session:
            total_changed += LeaveService(
                session
            ).reconcile_approved_leave(
                company_id=int(company_id)
            )

    print(
        "Leave credit reconciliation completed. "
        f"Updated requests: {total_changed}"
    )


if __name__ == "__main__":
    main()
