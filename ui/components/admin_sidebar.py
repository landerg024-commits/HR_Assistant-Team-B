"""Reusable administrator sidebar navigation.

Navigation is centralized here so adding or removing admin modules does not
require changes in every page.
"""

import streamlit as st

from authentication.current_user import AuthenticatedUser
from authentication.session_manager import AuthSessionManager
from ui.navigation_state import set_navigation_state


ADMIN_NAVIGATION = (
    "Admin Dashboard",
    "Company Profile",
    "Employees",
    "Policies",
    "Leave Management",
    "Announcements",
    "Reports",
    "Audit Logs",
    "Integrations",
)



def render_admin_sidebar(
    assistant_name: str,
    current_user: AuthenticatedUser,
) -> None:
    """Render admin navigation, portal switch, and logout."""

    st.sidebar.markdown(
        f"<div class='hr-brand'>🤖 {assistant_name}</div>",
        unsafe_allow_html=True,
    )
    st.sidebar.caption("Administration Portal")
    st.sidebar.caption(
        current_user.employee_name or current_user.username
    )
    st.sidebar.divider()

    # Department names are managed directly from Employee Add/Edit.
    # Redirect older refresh-safe Department bookmarks to Employees.
    if st.session_state.current_page == "Departments":
        set_navigation_state(
            portal_mode="admin",
            current_page="Employees",
        )
        st.rerun()

    if st.session_state.current_page not in ADMIN_NAVIGATION:
        st.session_state.current_page = "Admin Dashboard"

    for page_name in ADMIN_NAVIGATION:
        button_type = (
            "primary"
            if st.session_state.current_page == page_name
            else "secondary"
        )

        if st.sidebar.button(
            page_name,
            use_container_width=True,
            type=button_type,
            key=f"admin_nav_{page_name}",
        ):
            set_navigation_state(
                portal_mode="admin",
                current_page=page_name,
            )
            st.rerun()

    st.sidebar.divider()

    if st.sidebar.button(
        "Employee Portal",
        use_container_width=True,
        key="employee_portal_button",
    ):
        set_navigation_state(
            portal_mode="employee",
            current_page="Dashboard",
        )
        st.rerun()

    if st.sidebar.button(
        "Log Out",
        use_container_width=True,
        key="admin_logout_button",
    ):
        AuthSessionManager.logout()
