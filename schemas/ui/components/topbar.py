"""Reusable authenticated application top bar."""

import streamlit as st

from authentication.current_user import AuthenticatedUser


def render_topbar(
    company_name: str,
    current_user: AuthenticatedUser,
    section_name: str = "Employee HR Services",
) -> None:
    """Display company, portal section, user, and role."""

    display_name = (
        current_user.employee_name or current_user.username
    )

    st.markdown(
        f"""
        <div class="hr-topbar">
            <div>
                <div class="hr-brand">{company_name}</div>
                <div class="hr-muted">{section_name}</div>
            </div>
            <div class="hr-muted">
                {display_name} · {current_user.role_name}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
