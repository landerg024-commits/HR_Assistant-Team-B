"""In-app notification business logic for the top-bar bell."""

from sqlalchemy.orm import Session

from models.notification import Notification
from repositories.notification_repository import NotificationRepository


class NotificationService:
    """Create, read, and mark user notifications."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = NotificationRepository(session)

    def create(self, *, company_id: int, user_id: int, event_type: str, title: str, message: str, related_entity_type: str | None = None, related_entity_id: int | None = None) -> Notification:
        notification = Notification(
            company_id=company_id,
            user_id=user_id,
            event_type=event_type,
            title=title.strip(),
            message=message.strip(),
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
            is_read=False,
        )
        self.session.add(notification)
        return notification

    def unread_count(self, *, company_id: int, user_id: int) -> int:
        return self.repository.unread_count(company_id=company_id, user_id=user_id)

    def list_recent(self, *, company_id: int, user_id: int, limit: int = 10):
        return self.repository.list_recent(company_id=company_id, user_id=user_id, limit=limit)

    def mark_all_read(self, *, company_id: int, user_id: int) -> int:
        return self.repository.mark_all_read(company_id=company_id, user_id=user_id)
