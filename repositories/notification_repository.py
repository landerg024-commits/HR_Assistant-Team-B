"""Queries for the authenticated notification bell."""

from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from models.notification import Notification
from repositories.base_repository import BaseRepository


class NotificationRepository(BaseRepository[Notification]):
    """Company/user-scoped notification persistence."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Notification)

    def unread_count(self, *, company_id: int, user_id: int) -> int:
        return int(
            self.session.scalar(
                select(func.count(Notification.id)).where(
                    Notification.company_id == company_id,
                    Notification.user_id == user_id,
                    Notification.is_read.is_(False),
                )
            )
            or 0
        )

    def list_recent(self, *, company_id: int, user_id: int, limit: int = 10) -> list[Notification]:
        statement = (
            select(Notification)
            .where(
                Notification.company_id == company_id,
                Notification.user_id == user_id,
            )
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(limit)
        )
        return list(self.session.scalars(statement).all())

    def mark_all_read(self, *, company_id: int, user_id: int) -> int:
        result = self.session.execute(
            update(Notification)
            .where(
                Notification.company_id == company_id,
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
            .values(is_read=True, read_at=datetime.now(timezone.utc))
        )
        self.session.commit()
        return int(result.rowcount or 0)
