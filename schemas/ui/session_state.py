"""Initialize shared Streamlit session-state values."""

import streamlit as st

from authentication.session_manager import AuthSessionManager
from config.settings import get_settings
from core.constants import DEFAULT_PAGE, SUPPORTED_THEMES


def initialize_session_state() -> None:
    """Create theme, navigation, portal, and authentication keys."""

    settings = get_settings()

    if "theme" not in st.session_state:
        selected_theme = settings.default_theme.lower()

        st.session_state.theme = (
            selected_theme
            if selected_theme in SUPPORTED_THEMES
            else "light"
        )

    if "current_page" not in st.session_state:
        st.session_state.current_page = DEFAULT_PAGE

    if "portal_mode" not in st.session_state:
        st.session_state.portal_mode = "employee"

    AuthSessionManager.initialize()
