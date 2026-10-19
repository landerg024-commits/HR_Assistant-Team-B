"""Database queries for single-use password-reset tokens."""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from models.password_reset_token import PasswordResetToken
from repositories.base_repository import BaseRepository


class PasswordResetTokenRepository(
    BaseRepository[PasswordResetToken]
):
    """Repository for password-reset request records."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, PasswordResetToken)

    def get_by_hash(
        self,
        token_hash: str,
        *,
        for_update: bool = False,
    ) -> PasswordResetToken | None:
        """Find one reset record by its irreversible token hash."""

        statement = select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash
        )

        if for_update:
            statement = statement.with_for_update()

        return self.session.scalar(statement)

    def get_latest_for_user(
        self,
        *,
        company_id: int,
        user_id: int,
    ) -> PasswordResetToken | None:
        """Return the newest reset request for cooldown checks."""

        statement = (
            select(PasswordResetToken)
            .where(
                PasswordResetToken.company_id == company_id,
                PasswordResetToken.user_id == user_id,
            )
            .order_by(
                PasswordResetToken.requested_at.desc()
            )
            .limit(1)
        )

        return self.session.scalar(statement)

    def revoke_active_for_user(
        self,
        *,
        company_id: int,
        user_id: int,
        revoked_at: datetime,
        exclude_token_id: int | None = None,
    ) -> None:
        """Revoke all unused reset links for one account."""

        conditions = [
            PasswordResetToken.company_id == company_id,
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.revoked_at.is_(None),
        ]

        if exclude_token_id is not None:
            conditions.append(
                PasswordResetToken.id != exclude_token_id
            )

        self.session.execute(
            update(PasswordResetToken)
            .where(*conditions)
            .values(revoked_at=revoked_at)
            .execution_options(
                synchronize_session=False
            )
        )
