"""Streamlit authentication-session management.

Only safe identity data is stored. Passwords and hashes never enter
Streamlit session state.
"""

import streamlit as st

from authentication.current_user import AuthenticatedUser


class AuthSessionManager:
    """Create, update, and clear authentication session state."""

    AUTHENTICATED_KEY = "is_authenticated"
    USER_KEY = "authenticated_user"

    @classmethod
    def initialize(cls) -> None:
        """Create required session keys for a new browser session."""

        if cls.AUTHENTICATED_KEY not in st.session_state:
            st.session_state[cls.AUTHENTICATED_KEY] = False

        if cls.USER_KEY not in st.session_state:
            st.session_state[cls.USER_KEY] = None

    @classmethod
    def login(cls, user: AuthenticatedUser) -> None:
        """Save the logged-in user's safe session representation."""

        st.session_state[cls.AUTHENTICATED_KEY] = True
        st.session_state[cls.USER_KEY] = user.to_session_dict()

    @classmethod
    def update_user(cls, user: AuthenticatedUser) -> None:
        """Refresh session data after a password or profile change."""

        st.session_state[cls.USER_KEY] = user.to_session_dict()

    @classmethod
    def logout(cls) -> None:
        """Clear authentication and return navigation to a safe page."""

        st.session_state[cls.AUTHENTICATED_KEY] = False
        st.session_state[cls.USER_KEY] = None
        st.session_state.current_page = "Chat Assistant"
        st.session_state.portal_mode = "employee"

    @classmethod
    def is_authenticated(cls) -> bool:
        """Return True only when login state and user data both exist."""

        return bool(
            st.session_state.get(cls.AUTHENTICATED_KEY)
            and st.session_state.get(cls.USER_KEY)
        )

    @classmethod
    def get_current_user(cls) -> AuthenticatedUser | None:
        """Return the typed logged-in user, or None when logged out."""

        values = st.session_state.get(cls.USER_KEY)

        if not values:
            return None

        return AuthenticatedUser.from_session_dict(values)
