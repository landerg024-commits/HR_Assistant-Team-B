"""Database queries for persistent authentication sessions."""

from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from models.auth_session import AuthSession
from repositories.base_repository import BaseRepository


class AuthSessionRepository(BaseRepository[AuthSession]):
    """Repository for revocable server-side login sessions."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, AuthSession)

    def get_by_token_hash(
        self,
        token_hash: str,
    ) -> AuthSession | None:
        """Return one session using its non-reversible token hash."""

        return self.session.scalar(
            select(AuthSession).where(
                AuthSession.token_hash == token_hash
            )
        )

    def revoke_by_token_hash(
        self,
        *,
        token_hash: str,
        revoked_at: datetime,
    ) -> bool:
        """Revoke one active session and return whether it existed."""

        record = self.get_by_token_hash(token_hash)

        if record is None:
            return False

        if record.revoked_at is None:
            record.revoked_at = revoked_at
            self.session.commit()

        return True

    def revoke_user_sessions(
        self,
        *,
        company_id: int,
        user_id: int,
        revoked_at: datetime,
    ) -> int:
        """Revoke every active session belonging to one user."""

        result = self.session.execute(
            update(AuthSession)
            .where(
                AuthSession.company_id == company_id,
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )
        self.session.commit()

        return int(result.rowcount or 0)

    def delete_expired(
        self,
        *,
        expired_before: datetime,
    ) -> int:
        """Remove expired rows to keep the session table compact."""

        result = self.session.execute(
            delete(AuthSession).where(
                AuthSession.expires_at < expired_before
            )
        )
        self.session.commit()

        return int(result.rowcount or 0)
