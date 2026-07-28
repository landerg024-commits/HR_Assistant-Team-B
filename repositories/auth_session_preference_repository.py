"""Database access for persistent theme preferences."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.auth_session_preference import AuthSessionPreference
from repositories.base_repository import BaseRepository


class AuthSessionPreferenceRepository(
    BaseRepository[AuthSessionPreference]
):
    """Repository for one preference row per auth session."""

    def __init__(self, session: Session) -> None:
        super().__init__(
            session,
            AuthSessionPreference,
        )

    def get_by_auth_session_id(
        self,
        auth_session_id: int,
    ) -> AuthSessionPreference | None:
        """Return the preference row for one browser session."""

        return self.session.scalar(
            select(AuthSessionPreference).where(
                AuthSessionPreference.auth_session_id
                == auth_session_id
            )
        )

    def create_or_update(
        self,
        *,
        auth_session_id: int,
        theme: str,
    ) -> AuthSessionPreference:
        """Insert or update the last selected theme."""

        preference = self.get_by_auth_session_id(
            auth_session_id
        )

        if preference is None:
            return self.create(
                {
                    "auth_session_id": auth_session_id,
                    "theme": theme,
                }
            )

        preference.theme = theme
        self.session.commit()
        self.session.refresh(preference)

        return preference
