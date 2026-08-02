"""Company-scoped persistence queries for smart planning reminders."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.event_reminder import EventReminder
from repositories.base_repository import BaseRepository


class EventReminderRepository(BaseRepository[EventReminder]):
    """Tenant-safe queries for active and archived event reminders."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, EventReminder)

    def list_for_admin(self, company_id: int) -> list[EventReminder]:
        """Return active reminder history ordered by event date."""

        statement = (
            select(EventReminder)
            .where(
                EventReminder.company_id == company_id,
                EventReminder.archived_at.is_(None),
            )
            .order_by(
                EventReminder.event_start_at.desc(),
                EventReminder.id.desc(),
            )
        )
        return list(self.session.scalars(statement).all())

    def list_archived(self, company_id: int) -> list[EventReminder]:
        """Return reminder plans currently retained in the Reminder Bin."""

        statement = (
            select(EventReminder)
            .where(
                EventReminder.company_id == company_id,
                EventReminder.archived_at.is_not(None),
            )
            .order_by(
                EventReminder.archived_at.desc(),
                EventReminder.id.desc(),
            )
        )
        return list(self.session.scalars(statement).all())

    def list_reconciliation_candidates(
        self,
        *,
        company_id: int,
        at: datetime,
    ) -> list[EventReminder]:
        """Return active upcoming plans close enough for fixed milestones."""

        statement = (
            select(EventReminder)
            .where(
                EventReminder.company_id == company_id,
                EventReminder.archived_at.is_(None),
                EventReminder.status.in_(("planned", "announcement_ready")),
                EventReminder.event_start_at >= at,
                EventReminder.event_start_at <= at + timedelta(days=32),
            )
            .order_by(
                EventReminder.event_start_at,
                EventReminder.id,
            )
        )
        return list(self.session.scalars(statement).all())
