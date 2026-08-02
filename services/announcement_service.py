"""Announcement publishing, storage, and dissemination logic."""

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from config.settings import Settings, get_settings
from models.announcement import Announcement
from modules.announcements.announcement_image_storage import (
    AnnouncementImageStorage,
)
from repositories.announcement_repository import (
    AnnouncementRepository,
)
from repositories.user_repository import UserRepository
from schemas.announcement_schema import AnnouncementInput
from services.notification_service import NotificationService


class AnnouncementService:
    """Manage company announcements and notify active users."""

    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repository = AnnouncementRepository(
            session
        )
        self.user_repository = UserRepository(session)
        self.notification_service = NotificationService(
            session
        )
        self.storage = AnnouncementImageStorage(
            self.settings.announcement_upload_dir
        )

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

    @staticmethod
    def display_status(
        announcement: Announcement,
        *,
        at: datetime | None = None,
    ) -> str:
        """Return a user-facing lifecycle label."""

        selected_time = at or datetime.now(
            timezone.utc
        )

        if announcement.status == "archived":
            return "Archived"

        if announcement.status == "draft":
            return "Draft"

        publish_at = AnnouncementService._as_utc(
            announcement.publish_at
        )
        expires_at = AnnouncementService._as_utc(
            announcement.expires_at
        )
        selected_time = (
            AnnouncementService._as_utc(selected_time)
            or datetime.now(timezone.utc)
        )

        if (
            publish_at is not None
            and publish_at > selected_time
        ):
            return "Scheduled"

        if (
            expires_at is not None
            and expires_at < selected_time
        ):
            return "Expired"

        return "Published"

    def _store_image(
        self,
        *,
        company_id: int,
        filename: str | None,
        file_bytes: bytes | None,
    ) -> str | None:
        """Validate and store an optional cover image."""

        if not file_bytes:
            return None

        if not filename:
            raise ValueError(
                "The announcement image filename is missing."
            )

        self.storage.validate(
            filename=filename,
            file_bytes=file_bytes,
            maximum_size_bytes=(
                self.settings.announcement_upload_max_mb
                * 1024
                * 1024
            ),
        )

        return self.storage.write(
            company_id=company_id,
            filename=filename,
            file_bytes=file_bytes,
        )

    def _queue_publication_notifications(
        self,
        announcement: Announcement,
        *,
        at: datetime,
    ) -> None:
        """Create one global-bell notification per active user."""

        user_ids = self.user_repository.list_active_ids(
            company_id=announcement.company_id,
            exclude_user_id=(
                announcement.created_by_user_id
            ),
        )

        for user_id in user_ids:
            self.notification_service.create(
                company_id=announcement.company_id,
                user_id=user_id,
                event_type="announcement_published",
                title=announcement.title,
                message=announcement.summary,
                related_entity_type="announcement",
                related_entity_id=announcement.id,
            )

        announcement.notification_sent_at = at

        if announcement.published_at is None:
            announcement.published_at = at

    def reconcile_publications(
        self,
        *,
        company_id: int,
        at: datetime | None = None,
    ) -> int:
        """Notify users when immediate or scheduled posts become active."""

        selected_time = at or self._now()
        due = self.repository.list_due_for_notification(
            company_id=company_id,
            at=selected_time,
        )

        for announcement in due:
            self._queue_publication_notifications(
                announcement,
                at=selected_time,
            )

        if due:
            self.session.commit()

        return len(due)

    def create(
        self,
        values: AnnouncementInput,
        *,
        actor_user_id: int,
        publish: bool,
        image_filename: str | None = None,
        image_bytes: bytes | None = None,
        image_mime_type: str | None = None,
    ) -> Announcement:
        """Create a draft or publish/schedule a new announcement."""

        storage_path = self._store_image(
            company_id=values.company_id,
            filename=image_filename,
            file_bytes=image_bytes,
        )
        now = self._now()
        publish_at = (
            values.publish_at
            if publish
            else values.publish_at
        )

        if publish and publish_at is None:
            publish_at = now

        announcement = Announcement(
            company_id=values.company_id,
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
            title=values.title,
            category=values.category,
            summary=values.summary,
            content=values.content,
            status=(
                "published"
                if publish
                else "draft"
            ),
            is_pinned=values.is_pinned,
            publish_at=publish_at,
            expires_at=values.expires_at,
            image_original_filename=(
                Path(image_filename).name
                if image_filename and image_bytes
                else None
            ),
            image_storage_path=storage_path,
            image_mime_type=(
                image_mime_type
                if image_bytes
                else None
            ),
            image_size_bytes=(
                len(image_bytes)
                if image_bytes
                else None
            ),
        )
        self.session.add(announcement)

        try:
            self.session.flush()
            announcement.public_id = (
                f"ANN_{announcement.id:06d}"
            )
            self.session.commit()
            self.session.refresh(announcement)

        except Exception:
            self.session.rollback()
            self.storage.delete(storage_path)
            raise

        if publish:
            self.reconcile_publications(
                company_id=values.company_id,
                at=now,
            )
            announcement = self.repository.get_by_id(
                announcement.id,
                values.company_id,
            )

        return announcement

    def update(
        self,
        *,
        announcement_id: int,
        values: AnnouncementInput,
        actor_user_id: int,
        publish: bool = False,
        archive: bool = False,
        restore_to_draft: bool = False,
        replacement_filename: str | None = None,
        replacement_bytes: bytes | None = None,
        replacement_mime_type: str | None = None,
        remove_image: bool = False,
    ) -> Announcement:
        """Edit content and optionally publish, archive, or restore it."""

        announcement = self.repository.get_by_id(
            announcement_id,
            values.company_id,
        )

        if announcement is None:
            raise ValueError(
                "The selected announcement is unavailable."
            )

        new_storage_path = self._store_image(
            company_id=values.company_id,
            filename=replacement_filename,
            file_bytes=replacement_bytes,
        )
        old_storage_path = announcement.image_storage_path
        now = self._now()

        announcement.title = values.title
        announcement.category = values.category
        announcement.summary = values.summary
        announcement.content = values.content
        announcement.is_pinned = values.is_pinned
        announcement.publish_at = values.publish_at
        announcement.expires_at = values.expires_at

        announcement.updated_by_user_id = actor_user_id

        if replacement_bytes:
            announcement.image_original_filename = (
                Path(replacement_filename).name
                if replacement_filename
                else "announcement_image"
            )
            announcement.image_storage_path = (
                new_storage_path
            )
            announcement.image_mime_type = (
                replacement_mime_type
            )
            announcement.image_size_bytes = len(
                replacement_bytes
            )
        elif remove_image:
            announcement.image_original_filename = None
            announcement.image_storage_path = None
            announcement.image_mime_type = None
            announcement.image_size_bytes = None

        if archive:
            announcement.status = "archived"
            announcement.archived_at = now
            announcement.is_pinned = False

        elif restore_to_draft:
            announcement.status = "draft"
            announcement.archived_at = None
            announcement.published_at = None
            announcement.notification_sent_at = None

        elif publish:
            announcement.status = "published"
            announcement.archived_at = None

            if announcement.publish_at is None:
                announcement.publish_at = now

        try:
            self.session.commit()
            self.session.refresh(announcement)

        except Exception:
            self.session.rollback()
            self.storage.delete(new_storage_path)
            raise

        if (
            (replacement_bytes or remove_image)
            and old_storage_path
            and old_storage_path
            != announcement.image_storage_path
        ):
            self.storage.delete(old_storage_path)

        if announcement.status == "published":
            self.reconcile_publications(
                company_id=values.company_id,
                at=now,
            )
            announcement = self.repository.get_by_id(
                announcement.id,
                values.company_id,
            )

        return announcement

    def move_to_archive(
        self,
        *,
        company_id: int,
        announcement_id: int,
        actor_user_id: int,
    ) -> Announcement:
        """Soft-delete an announcement by moving it to Archive."""

        announcement = self.repository.get_by_id(
            announcement_id,
            company_id,
        )

        if announcement is None:
            raise ValueError(
                "The selected announcement is unavailable."
            )

        if announcement.status == "archived":
            raise ValueError(
                "The selected announcement is already archived."
            )

        announcement.status = "archived"
        announcement.archived_at = self._now()
        announcement.updated_by_user_id = actor_user_id
        announcement.is_pinned = False

        self.session.commit()
        self.session.refresh(announcement)

        return announcement

    def restore_archived(
        self,
        *,
        company_id: int,
        announcement_id: int,
        actor_user_id: int,
    ) -> Announcement:
        """Restore an archived announcement as an editable draft."""

        announcement = self.repository.get_by_id(
            announcement_id,
            company_id,
        )

        if announcement is None:
            raise ValueError(
                "The selected announcement is unavailable."
            )

        if announcement.status != "archived":
            raise ValueError(
                "Only archived announcements can be restored."
            )

        announcement.status = "draft"
        announcement.archived_at = None
        announcement.published_at = None
        announcement.notification_sent_at = None
        announcement.updated_by_user_id = actor_user_id
        announcement.is_pinned = False

        self.session.commit()
        self.session.refresh(announcement)

        return announcement

    def list_for_admin(
        self,
        company_id: int,
    ) -> list[Announcement]:
        """Return company announcements for the admin workspace."""

        return self.repository.list_for_admin(
            company_id
        )

    def list_visible(
        self,
        *,
        company_id: int,
        limit: int | None = None,
        at: datetime | None = None,
    ) -> list[Announcement]:
        """Return employee-visible announcements."""

        return self.repository.list_visible(
            company_id=company_id,
            at=at or self._now(),
            limit=limit,
        )

    def read_image(
        self,
        announcement: Announcement,
    ) -> bytes:
        """Read one private cover image."""

        if not announcement.image_storage_path:
            raise FileNotFoundError(
                "This announcement has no image."
            )

        return self.storage.read(
            announcement.image_storage_path
        )
