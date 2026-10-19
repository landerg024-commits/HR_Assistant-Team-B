"""Database-backed login, navigation, and theme persistence service.

Authentication decides whether a session is valid. Navigation and theme
records restore the user's last interface state after browser refresh.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import secrets

from sqlalchemy.orm import Session

from authentication.current_user import AuthenticatedUser
from repositories.auth_session_navigation_repository import (
    AuthSessionNavigationRepository,
)
from repositories.auth_session_preference_repository import (
    AuthSessionPreferenceRepository,
)
from repositories.auth_session_repository import (
    AuthSessionRepository,
)


ADMIN_ROLE_NAMES = {
    "super_admin",
    "company_admin",
    "hr_admin",
}

SUPPORTED_THEMES = {
    "light",
    "dark",
}


@dataclass(slots=True)
class CreatedPersistentSession:
    """Values returned after creating a login session."""

    auth_session_id: int
    raw_token: str
    expires_at: datetime


@dataclass(slots=True)
class RestoredPersistentSession:
    """User and interface state restored after browser refresh."""

    auth_session_id: int
    current_user: AuthenticatedUser
    portal_mode: str
    current_page: str
    theme: str


class PersistentSessionService:
    """Create, validate, restore, update, and revoke sessions."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = AuthSessionRepository(session)
        self.navigation_repository = (
            AuthSessionNavigationRepository(session)
        )
        self.preference_repository = (
            AuthSessionPreferenceRepository(session)
        )

    @staticmethod
    def _utc_now() -> datetime:
        """Return naive UTC for SQLite/PostgreSQL comparison."""

        return datetime.now(UTC).replace(tzinfo=None)

    @staticmethod
    def hash_token(raw_token: str) -> str:
        """Hash a raw browser token before database use."""

        return hashlib.sha256(
            raw_token.encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _default_navigation_for_user(
        current_user: AuthenticatedUser,
    ) -> tuple[str, str]:
        """Return the role-appropriate starting route."""

        if current_user.role_name in ADMIN_ROLE_NAMES:
            return "admin", "Admin Dashboard"

        return "employee", "Chat Assistant"

    @staticmethod
    def _sanitize_theme(theme: str | None) -> str:
        """Return only a supported light/dark theme value."""

        normalized = (theme or "light").strip().lower()

        return (
            normalized
            if normalized in SUPPORTED_THEMES
            else "light"
        )

    def create_session(
        self,
        *,
        current_user: AuthenticatedUser,
        lifetime_days: int,
        portal_mode: str | None = None,
        current_page: str | None = None,
        theme: str = "light",
        user_agent: str | None = None,
    ) -> CreatedPersistentSession:
        """Create login, navigation, and theme records."""

        default_portal, default_page = (
            self._default_navigation_for_user(current_user)
        )

        portal_mode = portal_mode or default_portal
        current_page = current_page or default_page
        theme = self._sanitize_theme(theme)

        now = self._utc_now()
        expires_at = now + timedelta(days=lifetime_days)
        raw_token = secrets.token_urlsafe(48)

        auth_session = self.repository.create(
            {
                "company_id": current_user.company_id,
                "user_id": current_user.user_id,
                "token_hash": self.hash_token(raw_token),
                "expires_at": expires_at,
                "last_activity_at": now,
                "user_agent": (
                    user_agent[:500]
                    if user_agent
                    else None
                ),
            }
        )

        self.navigation_repository.create_or_update(
            auth_session_id=auth_session.id,
            portal_mode=portal_mode,
            current_page=current_page,
        )

        self.preference_repository.create_or_update(
            auth_session_id=auth_session.id,
            theme=theme,
        )

        return CreatedPersistentSession(
            auth_session_id=auth_session.id,
            raw_token=raw_token,
            expires_at=expires_at,
        )

    def _validate_auth_session(
        self,
        auth_session,
        *,
        idle_timeout_minutes: int,
    ) -> bool:
        """Check revocation, expiration, inactivity, and account status."""

        now = self._utc_now()

        if auth_session.revoked_at is not None:
            return False

        if auth_session.expires_at <= now:
            auth_session.revoked_at = now
            self.session.commit()
            return False

        idle_deadline = (
            auth_session.last_activity_at
            + timedelta(minutes=idle_timeout_minutes)
        )

        if idle_deadline <= now:
            auth_session.revoked_at = now
            self.session.commit()
            return False

        user = auth_session.user

        if (
            not user.is_active
            or not user.company.is_active
            or not user.role.is_active
        ):
            auth_session.revoked_at = now
            self.session.commit()
            return False

        auth_session.last_activity_at = now
        self.session.commit()

        return True

    def restore_session(
        self,
        *,
        raw_token: str,
        idle_timeout_minutes: int,
        default_theme: str = "light",
    ) -> RestoredPersistentSession | None:
        """Restore login, portal, exact page, and selected theme."""

        if not raw_token:
            return None

        auth_session = self.repository.get_by_token_hash(
            self.hash_token(raw_token)
        )

        if auth_session is None:
            return None

        if not self._validate_auth_session(
            auth_session,
            idle_timeout_minutes=idle_timeout_minutes,
        ):
            return None

        current_user = AuthenticatedUser.from_model(
            auth_session.user
        )

        navigation = (
            self.navigation_repository
            .get_by_auth_session_id(auth_session.id)
        )

        # Older sessions may not yet have a navigation row.
        if navigation is None:
            portal_mode, current_page = (
                self._default_navigation_for_user(current_user)
            )

            navigation = (
                self.navigation_repository.create_or_update(
                    auth_session_id=auth_session.id,
                    portal_mode=portal_mode,
                    current_page=current_page,
                )
            )

        preference = (
            self.preference_repository
            .get_by_auth_session_id(auth_session.id)
        )

        # Existing v6.1/v6.2 sessions receive the configured default once.
        if preference is None:
            preference = (
                self.preference_repository.create_or_update(
                    auth_session_id=auth_session.id,
                    theme=self._sanitize_theme(default_theme),
                )
            )

        return RestoredPersistentSession(
            auth_session_id=auth_session.id,
            current_user=current_user,
            portal_mode=navigation.portal_mode,
            current_page=navigation.current_page,
            theme=self._sanitize_theme(preference.theme),
        )

    def validate_session_id(
        self,
        *,
        auth_session_id: int,
        idle_timeout_minutes: int,
    ) -> bool:
        """Validate and touch an active Streamlit session."""

        auth_session = self.repository.get_by_id_with_user(
            auth_session_id
        )

        if auth_session is None:
            return False

        return self._validate_auth_session(
            auth_session,
            idle_timeout_minutes=idle_timeout_minutes,
        )

    def update_navigation(
        self,
        *,
        auth_session_id: int,
        portal_mode: str,
        current_page: str,
    ) -> None:
        """Save the exact valid route selected by the user."""

        self.navigation_repository.create_or_update(
            auth_session_id=auth_session_id,
            portal_mode=portal_mode,
            current_page=current_page,
        )

    def update_theme(
        self,
        *,
        auth_session_id: int,
        theme: str,
    ) -> str:
        """Validate and save the selected light/dark mode."""

        normalized_theme = self._sanitize_theme(theme)

        self.preference_repository.create_or_update(
            auth_session_id=auth_session_id,
            theme=normalized_theme,
        )

        return normalized_theme

    def revoke_token(
        self,
        raw_token: str | None,
    ) -> None:
        """Revoke the current browser token on logout."""

        if not raw_token:
            return

        self.repository.revoke_by_token_hash(
            token_hash=self.hash_token(raw_token),
            revoked_at=self._utc_now(),
        )

    def revoke_user_sessions(
        self,
        *,
        user_id: int,
        except_session_id: int | None = None,
    ) -> None:
        """Revoke all user sessions except an optional current one."""

        self.repository.revoke_user_sessions(
            user_id=user_id,
            revoked_at=self._utc_now(),
            except_session_id=except_session_id,
        )
