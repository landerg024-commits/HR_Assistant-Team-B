"""Coordinate login, cookie, route, and theme persistence."""

import streamlit as st

from authentication.access_control import AccessControl
from authentication.browser_cookie import BrowserSessionCookie
from authentication.current_user import AuthenticatedUser
from authentication.session_manager import AuthSessionManager
from config.settings import get_settings
from core.constants import (
    ADMIN_NAVIGATION,
    DEFAULT_ADMIN_PORTAL_PAGE,
    DEFAULT_EMPLOYEE_PORTAL_PAGE,
    SUPPORTED_THEMES,
    USER_NAVIGATION,
)
from database.session import SessionFactory
from services.persistent_session_service import (
    PersistentSessionService,
)


class PersistentLoginManager:
    """Manage login persistence and exact interface restoration."""

    @staticmethod
    def _default_navigation(
        current_user: AuthenticatedUser,
    ) -> tuple[str, str]:
        """Return the correct initial route for a user role."""

        if AccessControl.is_admin(current_user):
            return "admin", DEFAULT_ADMIN_PORTAL_PAGE

        return "employee", DEFAULT_EMPLOYEE_PORTAL_PAGE

    @staticmethod
    def _sanitize_navigation(
        *,
        current_user: AuthenticatedUser,
        portal_mode: str,
        current_page: str,
    ) -> tuple[str, str]:
        """Reject stale, invalid, or unauthorized saved routes."""

        if (
            portal_mode == "admin"
            and AccessControl.is_admin(current_user)
        ):
            page = (
                current_page
                if current_page in ADMIN_NAVIGATION
                else DEFAULT_ADMIN_PORTAL_PAGE
            )

            return "admin", page

        page = (
            current_page
            if current_page in USER_NAVIGATION
            else DEFAULT_EMPLOYEE_PORTAL_PAGE
        )

        return "employee", page

    @staticmethod
    def _sanitize_theme(theme: str | None) -> str:
        """Return only a supported application theme."""

        normalized = (theme or "light").lower()

        return (
            normalized
            if normalized in SUPPORTED_THEMES
            else "light"
        )

    @staticmethod
    def start(current_user: AuthenticatedUser) -> None:
        """Create persistent login and initial interface state."""

        settings = get_settings()

        portal_mode, current_page = (
            PersistentLoginManager._default_navigation(
                current_user
            )
        )

        theme = PersistentLoginManager._sanitize_theme(
            st.session_state.get(
                "theme",
                settings.default_theme,
            )
        )

        with SessionFactory() as session:
            created = PersistentSessionService(
                session
            ).create_session(
                current_user=current_user,
                lifetime_days=settings.auth_session_days,
                portal_mode=portal_mode,
                current_page=current_page,
                theme=theme,
            )

        BrowserSessionCookie().set_token(
            raw_token=created.raw_token,
            expires_at=created.expires_at,
        )

        AuthSessionManager.login(
            current_user,
            persistent_session_id=created.auth_session_id,
        )

        st.session_state.portal_mode = portal_mode
        st.session_state.current_page = current_page
        st.session_state.theme = theme

    @staticmethod
    def restore() -> bool:
        """Restore login, portal, exact page, and selected theme."""

        cookie = BrowserSessionCookie()
        raw_token = cookie.get_token()

        if not raw_token:
            return False

        settings = get_settings()

        with SessionFactory() as session:
            restored = PersistentSessionService(
                session
            ).restore_session(
                raw_token=raw_token,
                idle_timeout_minutes=(
                    settings.auth_session_idle_minutes
                ),
                default_theme=settings.default_theme,
            )

        if restored is None:
            cookie.remove_token()
            return False

        portal_mode, current_page = (
            PersistentLoginManager._sanitize_navigation(
                current_user=restored.current_user,
                portal_mode=restored.portal_mode,
                current_page=restored.current_page,
            )
        )

        theme = PersistentLoginManager._sanitize_theme(
            restored.theme
        )

        AuthSessionManager.login(
            restored.current_user,
            persistent_session_id=restored.auth_session_id,
        )

        st.session_state.portal_mode = portal_mode
        st.session_state.current_page = current_page
        st.session_state.theme = theme

        if (
            portal_mode != restored.portal_mode
            or current_page != restored.current_page
        ):
            with SessionFactory() as session:
                PersistentSessionService(
                    session
                ).update_navigation(
                    auth_session_id=restored.auth_session_id,
                    portal_mode=portal_mode,
                    current_page=current_page,
                )

        return True

    @staticmethod
    def save_navigation(
        *,
        portal_mode: str,
        current_page: str,
    ) -> None:
        """Validate and persist the selected portal and page."""

        current_user = AuthSessionManager.get_current_user()
        auth_session_id = (
            AuthSessionManager.get_persistent_session_id()
        )

        if current_user is None or auth_session_id is None:
            return

        portal_mode, current_page = (
            PersistentLoginManager._sanitize_navigation(
                current_user=current_user,
                portal_mode=portal_mode,
                current_page=current_page,
            )
        )

        st.session_state.portal_mode = portal_mode
        st.session_state.current_page = current_page

        with SessionFactory() as session:
            PersistentSessionService(
                session
            ).update_navigation(
                auth_session_id=auth_session_id,
                portal_mode=portal_mode,
                current_page=current_page,
            )

    @staticmethod
    def save_theme(theme: str) -> str:
        """Persist and apply the selected theme for this browser."""

        normalized_theme = (
            PersistentLoginManager._sanitize_theme(theme)
        )

        st.session_state.theme = normalized_theme

        auth_session_id = (
            AuthSessionManager.get_persistent_session_id()
        )

        if auth_session_id is None:
            return normalized_theme

        with SessionFactory() as session:
            PersistentSessionService(
                session
            ).update_theme(
                auth_session_id=auth_session_id,
                theme=normalized_theme,
            )

        return normalized_theme

    @staticmethod
    def validate_current_session() -> bool:
        """Validate expiration, inactivity, and revocation."""

        auth_session_id = (
            AuthSessionManager.get_persistent_session_id()
        )

        if auth_session_id is None:
            return False

        settings = get_settings()

        with SessionFactory() as session:
            is_valid = PersistentSessionService(
                session
            ).validate_session_id(
                auth_session_id=auth_session_id,
                idle_timeout_minutes=(
                    settings.auth_session_idle_minutes
                ),
            )

        if is_valid:
            return True

        BrowserSessionCookie().remove_token()
        AuthSessionManager.logout()

        return False

    @staticmethod
    def logout() -> None:
        """Revoke token, remove cookie, and clear login state."""

        cookie = BrowserSessionCookie()
        raw_token = cookie.get_token()

        with SessionFactory() as session:
            PersistentSessionService(
                session
            ).revoke_token(raw_token)

        cookie.remove_token()
        AuthSessionManager.logout()

    @staticmethod
    def revoke_other_sessions(
        user_id: int,
    ) -> None:
        """Keep this browser and revoke other device sessions."""

        current_session_id = (
            AuthSessionManager.get_persistent_session_id()
        )

        with SessionFactory() as session:
            PersistentSessionService(
                session
            ).revoke_user_sessions(
                user_id=user_id,
                except_session_id=current_session_id,
            )
