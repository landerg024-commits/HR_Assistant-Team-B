"""Protected administrator layout and page router."""

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
from ui.pages.admin.company_page import render_company_page
from ui.pages.admin.employees_page import render_employees_page
from ui.pages.admin.policies_page import render_admin_policies_page
from ui.pages.admin.integrations_page import render_integrations_page
from ui.pages.admin.leave_management_page import render_admin_leave_management_page


def render_admin_layout(
    settings: Settings,
    current_user: AuthenticatedUser,
) -> None:
    """Authorize and render the selected administrator module."""

    # Defense in depth: admin routing and the layout both check access.
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

    page = st.session_state.current_page

    if page == "Admin Dashboard":
        render_admin_dashboard_page(current_user)
    elif page == "Company Profile":
        render_company_page(current_user)
    elif page == "Employees":
        render_employees_page(current_user)
    elif page == "Policies":
        render_admin_policies_page(current_user)
    elif page == "Leave Management":
        render_admin_leave_management_page(current_user)
    elif page == "Integrations":
        render_integrations_page(current_user)
    else:
        render_admin_placeholder_page(page)
