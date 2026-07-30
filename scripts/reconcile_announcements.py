"""Publish due announcements and create user notifications."""

from sqlalchemy import select

from database.runtime_schema import initialize_runtime_schema
from database.session import SessionFactory
from models.company import Company
from services.announcement_service import AnnouncementService


def main() -> None:
    """Reconcile scheduled announcements for every active company."""

    initialize_runtime_schema()

    with SessionFactory() as session:
        company_ids = list(
            session.scalars(
                select(Company.id).where(
                    Company.is_active.is_(True)
                )
            ).all()
        )

    total_published = 0

    for company_id in company_ids:
        with SessionFactory() as session:
            total_published += AnnouncementService(
                session
            ).reconcile_publications(
                company_id=int(company_id)
            )

    print(
        "Announcement reconciliation completed. "
        f"Newly disseminated: {total_published}"
    )


if __name__ == "__main__":
    main()
