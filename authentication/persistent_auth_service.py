"""Issue, validate, rotate, and revoke persistent login sessions.

This service provides refresh-safe authentication without storing passwords
or raw tokens in the database.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import secrets

from sqlalchemy.orm import Session

from authentication.current_user import AuthenticatedUser
from config.settings import get_settings
from models.auth_session import AuthSession
from repositories.auth_session_repository import (
    AuthSessionRepository,
)
from repositories.user_repository import UserRepository


class PersistentSessionError(ValueError):
    """Raised when a browser session token is invalid or unavailable."""


def _utc_now() -> datetime:
    """Return one timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite-naive or timezone-aware timestamps to UTC."""

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


class PersistentAuthService:
    """Manage revocable, company-scoped authentication sessions."""

    def __init__(
        self,
        session: Session,
        session_hours: int | None = None,
    ) -> None:
        self.session = session
        self.repository = AuthSessionRepository(session)
        self.user_repository = UserRepository(session)
        self.session_hours = (
            session_hours
            if session_hours is not None
            else get_settings().auth_session_hours
        )

        if self.session_hours <= 0:
            raise ValueError(
                "Authentication session duration must be positive."
            )

        # Database schema creation happens once during app startup through
        # database.runtime_schema.initialize_runtime_schema(). Keeping DDL
        # outside this active login transaction avoids SQLite locking and
        # partial session-creation failures.

    @staticmethod
    def hash_token(raw_token: str) -> str:
        """Create the irreversible database representation of a token."""

        return hashlib.sha256(
            raw_token.encode("utf-8")
        ).hexdigest()

    def issue_session(
        self,
        current_user: AuthenticatedUser,
    ) -> str:
        """Create one random browser token and store only its hash."""

        user = self.user_repository.get_for_password_change(
            company_id=current_user.company_id,
            user_id=current_user.user_id,
        )

        if (
            user is None
            or not user.is_active
            or not user.company.is_active
            or not user.role.is_active
        ):
            raise PersistentSessionError(
                "The user account cannot start a persistent session."
            )

        now = _utc_now()
        raw_token = secrets.token_urlsafe(48)

        self.repository.create(
            {
                "company_id": user.company_id,
                "user_id": user.id,
                "token_hash": self.hash_token(raw_token),
                "expires_at": (
                    now + timedelta(hours=self.session_hours)
                ),
                "last_used_at": now,
                "revoked_at": None,
            }
        )

        # Opportunistic cleanup; failure is not security-critical.
        try:
            self.repository.delete_expired(
                expired_before=now - timedelta(days=1)
            )
        except Exception:
            self.session.rollback()

        return raw_token

    def restore_session(
        self,
        raw_token: str,
    ) -> AuthenticatedUser:
        """Validate a token and return refreshed safe user data."""

        if not raw_token or len(raw_token) < 32:
            raise PersistentSessionError(
                "The login session token is invalid."
            )

        token_hash = self.hash_token(raw_token)
        record = self.repository.get_by_token_hash(token_hash)

        if record is None or record.revoked_at is not None:
            raise PersistentSessionError(
                "The login session is unavailable."
            )

        now = _utc_now()

        if _as_utc(record.expires_at) <= now:
            record.revoked_at = now
            self.session.commit()
            raise PersistentSessionError(
                "The login session has expired."
            )

        user = self.user_repository.get_for_password_change(
            company_id=record.company_id,
            user_id=record.user_id,
        )

        if (
            user is None
            or not user.is_active
            or not user.company.is_active
            or not user.role.is_active
            or user.company_id != record.company_id
        ):
            record.revoked_at = now
            self.session.commit()
            raise PersistentSessionError(
                "The account is no longer authorized."
            )

        record.last_used_at = now
        self.session.commit()

        return AuthenticatedUser.from_model(user)

    def revoke_session(self, raw_token: str | None) -> None:
        """Revoke one token when a user explicitly logs out."""

        if not raw_token:
            return

        self.repository.revoke_by_token_hash(
            token_hash=self.hash_token(raw_token),
            revoked_at=_utc_now(),
        )

    def rotate_user_sessions(
        self,
        current_user: AuthenticatedUser,
    ) -> str:
        """Revoke old sessions and issue a new one after password change."""

        self.repository.revoke_user_sessions(
            company_id=current_user.company_id,
            user_id=current_user.user_id,
            revoked_at=_utc_now(),
        )

        return self.issue_session(current_user)
