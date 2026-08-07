"""Protected employee application layout."""

import streamlit as st

from authentication.current_user import AuthenticatedUser
from config.settings import Settings
from ui.components.sidebar import render_sidebar
from ui.components.topbar import render_topbar
from ui.pages.user.chat_page import render_chat_page
from ui.pages.user.company_forms_documents_page import (
    render_employee_company_forms_documents_page,
)
from ui.pages.user.dashboard_page import (
    render_employee_dashboard_page,
)
from ui.pages.user.placeholder_page import render_placeholder_page
from ui.pages.user.policies_page import render_employee_policies_page
from ui.pages.user.leave_management_page import render_employee_leave_management_page


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

    if current_page in {
        "Dashboard",
        "Company Announcements",
    }:
        # Legacy Company Announcements URLs now open the merged Dashboard.
        if current_page != "Dashboard":
            st.session_state.current_page = "Dashboard"
            st.query_params["page"] = "Dashboard"
        render_employee_dashboard_page(current_user)
    elif current_page == "Chat Assistant":
        render_chat_page(current_user)
    elif current_page == "Company Form/Documents":
        render_employee_company_forms_documents_page(current_user)
    elif current_page == "Company Policies":
        render_employee_policies_page(current_user)
    elif current_page in {"Leave Management", "My Requests"}:
        render_employee_leave_management_page(current_user)
    else:
        render_placeholder_page(current_page)
