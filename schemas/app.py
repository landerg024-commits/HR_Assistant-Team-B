"""AI HR Assistant Streamlit entry point.

Routing:
1. Initialize UI and authentication state.
2. Apply the selected theme.
3. Show login when logged out.
4. Force temporary-password replacement.
5. Route administrators and employees to protected layouts.
"""

import streamlit as st

from authentication.access_control import AccessControl
from authentication.session_manager import AuthSessionManager
from config.settings import get_settings
from ui.layouts.admin_layout import render_admin_layout
from ui.layouts.auth_layout import (
    render_login_layout,
    render_password_change_layout,
)
from ui.layouts.user_layout import render_user_layout
from ui.session_state import initialize_session_state
from ui.theme.theme_loader import apply_theme


def main() -> None:
    """Start the application and route the current browser session."""

    settings = get_settings()

    st.set_page_config(
        page_title=settings.app_name,
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    initialize_session_state()
    apply_theme()

    if not AuthSessionManager.is_authenticated():
        render_login_layout(settings)
        return

    current_user = AuthSessionManager.get_current_user()

    if current_user is None:
        AuthSessionManager.logout()
        st.rerun()

    if current_user.must_change_password:
        render_password_change_layout(
            settings,
            current_user,
        )
        return

    portal_mode = st.session_state.get(
        "portal_mode",
        "admin"
        if AccessControl.is_admin(current_user)
        else "employee",
    )

    if (
        portal_mode == "admin"
        and AccessControl.is_admin(current_user)
    ):
        render_admin_layout(settings, current_user)
        return

    render_user_layout(settings, current_user)


if __name__ == "__main__":
    main()
