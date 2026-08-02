"""Smart event-planning reminders and admin notification milestones."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from config.settings import Settings, get_settings
from models.event_reminder import EventReminder
from repositories.announcement_repository import AnnouncementRepository
from repositories.event_reminder_repository import EventReminderRepository
from repositories.user_repository import UserRepository
from schemas.event_reminder_schema import (
    EventReminderInput,
    automatic_reminder_schedule,
)
from services.notification_service import NotificationService


MILESTONE_SENT_FIELDS = {
    "1 month before": "reminder_one_month_sent_at",
    "2 weeks before": "reminder_two_weeks_sent_at",
    "1 week before": "reminder_one_week_sent_at",
}


class EventReminderService:
    """Manage independent event plans and their three automatic reminders."""

    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repository = EventReminderRepository(session)
        self.announcement_repository = AnnouncementRepository(session)
        self.user_repository = UserRepository(session)
        self.notification_service = NotificationService(session)

    @staticmethod
    def _now() -> datetime:
        """Return an aware UTC timestamp."""

        return datetime.now(timezone.utc)

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        """Normalize SQLite naive timestamps to aware UTC values."""

        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _validate_announcement_link(
        self,
        *,
        company_id: int,
        announcement_id: int | None,
    ) -> None:
        """Ensure an optional linked announcement belongs to the company."""

        if announcement_id is None:
            return
        if self.announcement_repository.get_by_id(
            announcement_id,
            company_id,
        ) is None:
            raise ValueError("The selected linked announcement is unavailable.")

    def _format_event_date(self, value: datetime) -> str:
        """Format one event date for an admin notification."""

        selected = self._as_utc(value) or value
        return selected.astimezone(
            ZoneInfo(self.settings.display_timezone)
        ).strftime("%B %d, %Y")

    @staticmethod
    def milestone_schedule(
        reminder: EventReminder,
    ) -> tuple[tuple[str, datetime, str], ...]:
        """Return each fixed milestone with its delivery-tracking field."""

        return tuple(
            (label, scheduled_at, MILESTONE_SENT_FIELDS[label])
            for label, scheduled_at in automatic_reminder_schedule(
                reminder.event_start_at
            )
        )

    @staticmethod
    def _reset_milestone_delivery(reminder: EventReminder) -> None:
        """Clear all fixed milestone delivery timestamps."""

        reminder.reminder_one_month_sent_at = None
        reminder.reminder_two_weeks_sent_at = None
        reminder.reminder_one_week_sent_at = None
        reminder.reminder_sent_at = None

    def create(
        self,
        values: EventReminderInput,
        *,
        actor_user_id: int,
    ) -> EventReminder:
        """Create one smart reminder with automatic fixed milestones."""

        self._validate_announcement_link(
            company_id=values.company_id,
            announcement_id=values.announcement_id,
        )
        one_month_at = values.reminder_schedule[0][1]
        reminder = EventReminder(
            company_id=values.company_id,
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
            title=values.title,
            category=values.category,
            notes=values.notes,
            event_start_at=values.event_start_at,
            event_end_at=values.event_end_at,
            reminder_lead_minutes=43200,
            reminder_at=one_month_at,
            reminder_sent_at=None,
            reminder_one_month_sent_at=None,
            reminder_two_weeks_sent_at=None,
            reminder_one_week_sent_at=None,
            status=values.status,
            announcement_id=values.announcement_id,
            archived_at=None,
            archived_by_user_id=None,
        )
        self.session.add(reminder)
        self.session.flush()
        reminder.public_id = f"REM_{reminder.id:06d}"
        self.session.commit()
        self.session.refresh(reminder)
        return reminder

    def update(
        self,
        *,
        reminder_id: int,
        values: EventReminderInput,
        actor_user_id: int,
    ) -> EventReminder:
        """Update one active reminder and reset milestones if its date changes."""

        reminder = self.repository.get_by_id(
            reminder_id,
            values.company_id,
        )
        if reminder is None or reminder.archived_at is not None:
            raise ValueError("The selected reminder is unavailable.")

        self._validate_announcement_link(
            company_id=values.company_id,
            announcement_id=values.announcement_id,
        )
        old_event_start = self._as_utc(reminder.event_start_at)
        new_event_start = self._as_utc(values.event_start_at)

        reminder.title = values.title
        reminder.category = values.category
        reminder.notes = values.notes
        reminder.event_start_at = values.event_start_at
        reminder.event_end_at = values.event_end_at
        reminder.reminder_lead_minutes = 43200
        reminder.reminder_at = values.reminder_schedule[0][1]
        reminder.status = values.status
        reminder.announcement_id = values.announcement_id
        reminder.updated_by_user_id = actor_user_id

        if old_event_start != new_event_start:
            self._reset_milestone_delivery(reminder)

        if values.status in {"completed", "cancelled"}:
            self._reset_milestone_delivery(reminder)

        self.session.commit()
        self.session.refresh(reminder)
        return reminder

    def move_to_bin(
        self,
        *,
        company_id: int,
        reminder_id: int,
        actor_user_id: int,
    ) -> EventReminder:
        """Soft-delete one reminder into the recoverable Reminder Bin."""

        reminder = self.repository.get_by_id(reminder_id, company_id)
        if reminder is None or reminder.archived_at is not None:
            raise ValueError("The selected reminder is unavailable.")
        reminder.archived_at = self._now()
        reminder.archived_by_user_id = actor_user_id
        reminder.updated_by_user_id = actor_user_id
        self.session.commit()
        self.session.refresh(reminder)
        return reminder

    def restore_from_bin(
        self,
        *,
        company_id: int,
        reminder_id: int,
        actor_user_id: int,
    ) -> EventReminder:
        """Restore one reminder from the Bin to active history."""

        reminder = self.repository.get_by_id(reminder_id, company_id)
        if reminder is None or reminder.archived_at is None:
            raise ValueError("The selected archived reminder is unavailable.")
        reminder.archived_at = None
        reminder.archived_by_user_id = None
        reminder.updated_by_user_id = actor_user_id
        self.session.commit()
        self.session.refresh(reminder)
        return reminder

    def permanently_delete(
        self,
        *,
        company_id: int,
        reminder_id: int,
    ) -> None:
        """Permanently delete only an item already stored in the Bin."""

        reminder = self.repository.get_by_id(reminder_id, company_id)
        if reminder is None or reminder.archived_at is None:
            raise ValueError(
                "Move the reminder to the Reminder Bin before permanent deletion."
            )
        self.repository.delete(reminder)

    def list_for_admin(self, company_id: int) -> list[EventReminder]:
        """Return non-archived reminders for year-based history."""

        return self.repository.list_for_admin(company_id)

    def list_archived(self, company_id: int) -> list[EventReminder]:
        """Return reminders retained in the Reminder Bin."""

        return self.repository.list_archived(company_id)

    def reconcile_due(
        self,
        *,
        company_id: int,
        at: datetime | None = None,
    ) -> int:
        """Send each unsent one-month, two-week, and one-week milestone."""

        selected_time = self._as_utc(at or self._now()) or self._now()
        candidates = self.repository.list_reconciliation_candidates(
            company_id=company_id,
            at=selected_time,
        )
        admin_ids = self.user_repository.list_active_admin_ids(
            company_id=company_id
        )
        reminders_notified = 0

        for reminder in candidates:
            # Send only the most recent milestone that is currently due.
            # This prevents a newly entered near-term event from producing
            # several catch-up notifications at the same time. Earlier missed
            # milestones remain visible as missed history in the UI.
            due_milestones = []
            for label, scheduled_at, sent_field in self.milestone_schedule(reminder):
                scheduled_utc = self._as_utc(scheduled_at) or scheduled_at
                if scheduled_utc <= selected_time:
                    due_milestones.append((label, scheduled_at, sent_field))

            if not due_milestones:
                continue

            label, _, sent_field = due_milestones[-1]
            if getattr(reminder, sent_field) is not None:
                continue

            event_label = self._format_event_date(reminder.event_start_at)
            for user_id in admin_ids:
                self.notification_service.create(
                    company_id=company_id,
                    user_id=user_id,
                    event_type="event_planning_reminder",
                    title=f"{label}: Prepare announcement — {reminder.title}",
                    message=(
                        f"{reminder.category} is scheduled for {event_label}. "
                        "Open Announcements > Reminders to review the "
                        "preparation notes."
                    ),
                    related_entity_type="event_reminder",
                    related_entity_id=reminder.id,
                )
            setattr(reminder, sent_field, selected_time)
            reminder.reminder_sent_at = selected_time
            reminders_notified += 1

        if reminders_notified:
            self.session.commit()

        return reminders_notified
