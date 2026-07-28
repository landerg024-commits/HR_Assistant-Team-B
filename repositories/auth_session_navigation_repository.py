"""Database access for persistent page and portal state."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.auth_session_navigation import AuthSessionNavigation
from repositories.base_repository import BaseRepository


class AuthSessionNavigationRepository(
    BaseRepository[AuthSessionNavigation]
):
    """Repository for one navigation row per auth session."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, AuthSessionNavigation)

    def get_by_auth_session_id(
        self,
        auth_session_id: int,
    ) -> AuthSessionNavigation | None:
        """Return the saved route for one browser session."""

        return self.session.scalar(
            select(AuthSessionNavigation).where(
                AuthSessionNavigation.auth_session_id
                == auth_session_id
            )
        )

    def create_or_update(
        self,
        *,
        auth_session_id: int,
        portal_mode: str,
        current_page: str,
    ) -> AuthSessionNavigation:
        """Insert or update the last selected portal and page."""

        navigation = self.get_by_auth_session_id(
            auth_session_id
        )

        if navigation is None:
            return self.create(
                {
                    "auth_session_id": auth_session_id,
                    "portal_mode": portal_mode,
                    "current_page": current_page,
                }
            )

        navigation.portal_mode = portal_mode
        navigation.current_page = current_page
        self.session.commit()
        self.session.refresh(navigation)

        return navigation
