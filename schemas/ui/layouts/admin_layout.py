"""Protected administrator layout."""

import streamlit as st

from authentication.access_control import AccessControl
from authentication.current_user import AuthenticatedUser
from config.settings import Settings
from ui.components.admin_sidebar import render_admin_sidebar
from ui.components.topbar import render_topbar
from ui.pages.admin.admin_dashboard_page import (
    render_admin_dashboard_page,
)
from ui.pages.admin.admin_placeholder_page import (
    render_admin_placeholder_page,
)


def render_admin_layout(
    settings: Settings,
    current_user: AuthenticatedUser,
) -> None:
    """Render administrator navigation only for approved roles."""

    # Defense in depth: routing checks this role, and the layout checks again.
    AccessControl.require_admin(current_user)

    render_admin_sidebar(
        assistant_name=settings.assistant_name,
        current_user=current_user,
    )
    render_topbar(
        company_name=current_user.company_name,
        current_user=current_user,
        section_name="Administration Portal",
    )

    current_page = st.session_state.current_page

    if current_page == "Admin Dashboard":
        render_admin_dashboard_page(current_user)
    else:
        render_admin_placeholder_page(current_page)
