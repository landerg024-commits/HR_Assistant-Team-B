"""Protected employee application layout."""

import streamlit as st

from authentication.current_user import AuthenticatedUser
from config.settings import Settings
from ui.components.sidebar import render_sidebar
from ui.components.topbar import render_topbar
from ui.pages.user.chat_page import render_chat_page
from ui.pages.user.placeholder_page import render_placeholder_page


def render_user_layout(
    settings: Settings,
    current_user: AuthenticatedUser,
) -> None:
    """Render employee sidebar, topbar, and selected page."""

    render_sidebar(
        assistant_name=settings.assistant_name,
        current_user=current_user,
    )
    render_topbar(
        company_name=current_user.company_name,
        current_user=current_user,
    )

    current_page = st.session_state.current_page

    if current_page == "Chat Assistant":
        render_chat_page()
    else:
        render_placeholder_page(current_page)
