"""Company-scoped announcement persistence queries."""

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from models.announcement import Announcement
from repositories.base_repository import BaseRepository


class AnnouncementRepository(
    BaseRepository[Announcement]
):
    """Tenant-safe announcement queries."""

    def __init__(
        self,
        session: Session,
    ) -> None:
        super().__init__(
            session,
            Announcement,
        )

    def list_for_admin(
        self,
        company_id: int,
    ) -> list[Announcement]:
        """Return every company announcement for administration."""

        statement = (
            select(Announcement)
            .where(
                Announcement.company_id == company_id
            )
            .order_by(
                Announcement.status,
                Announcement.is_pinned.desc(),
                func.coalesce(
                    Announcement.publish_at,
                    Announcement.created_at,
                ).desc(),
                Announcement.id.desc(),
            )
        )

        return list(
            self.session.scalars(statement).all()
        )

    def list_visible(
        self,
        *,
        company_id: int,
        at: datetime,
        limit: int | None = None,
    ) -> list[Announcement]:
        """Return published announcements visible at one moment."""

        statement = (
            select(Announcement)
            .where(
                Announcement.company_id == company_id,
                Announcement.status == "published",
                or_(
                    Announcement.publish_at.is_(None),
                    Announcement.publish_at <= at,
                ),
                or_(
                    Announcement.expires_at.is_(None),
                    Announcement.expires_at >= at,
                ),
            )
            .order_by(
                Announcement.is_pinned.desc(),
                func.coalesce(
                    Announcement.publish_at,
                    Announcement.published_at,
                    Announcement.created_at,
                ).desc(),
                Announcement.id.desc(),
            )
        )

        if limit is not None:
            statement = statement.limit(limit)

        return list(
            self.session.scalars(statement).all()
        )

    def list_due_for_notification(
        self,
        *,
        company_id: int,
        at: datetime,
    ) -> list[Announcement]:
        """Return due published posts that have not notified users."""

        statement = (
            select(Announcement)
            .where(
                Announcement.company_id == company_id,
                Announcement.status == "published",
                Announcement.notification_sent_at.is_(None),
                or_(
                    Announcement.publish_at.is_(None),
                    Announcement.publish_at <= at,
                ),
                or_(
                    Announcement.expires_at.is_(None),
                    Announcement.expires_at >= at,
                ),
            )
            .order_by(
                Announcement.publish_at,
                Announcement.id,
            )
        )

        return list(
            self.session.scalars(statement).all()
        )
