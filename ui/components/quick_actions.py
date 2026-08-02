"""Reusable Employee and Admin HR Assistant quick actions."""

import streamlit as st

from ui.navigation_state import set_navigation_state


def render_quick_actions() -> None:
    """Render the Employee Portal quick-action cards."""

    st.subheader("Quick Actions")
    actions = [
        ("Apply for Leave", "Submit a new leave request"),
        ("Check Leave Balance", "View your leave entitlement"),
        ("Request Document", "Request an HR document"),
        ("Raise a Concern", "Report an issue or concern"),
    ]

    for title, text in actions:
        html = (
            '<div class="hr-card" '
            'style="min-height:auto;margin-bottom:12px">'
            f'<div class="hr-title">{title}</div>'
            f'<div class="hr-muted">{text}</div>'
            '</div>'
        )
        st.markdown(
            html,
            unsafe_allow_html=True,
        )


def _open_admin_quick_action(
    *,
    page: str,
    query_params: dict[str, str] | None = None,
) -> None:
    """Open one admin module and remove stale deep-link parameters."""

    for key in (
        "announcement_id",
        "employee_id",
        "leave_request_id",
        "leave_view",
        "policy_id",
    ):
        if key in st.query_params:
            del st.query_params[key]

    set_navigation_state(
        portal_mode="admin",
        current_page=page,
    )

    for key, value in (
        query_params or {}
    ).items():
        st.query_params[key] = value

    st.rerun()


def render_admin_quick_actions() -> None:
    """Render clickable admin actions using the Employee card pattern."""

    st.subheader("Quick Actions")

    actions = (
        (
            "Manage Employees",
            "Create, edit, search, or review employee records",
            "Employees",
            {},
        ),
        (
            "Review Leave Requests",
            "Open the company leave-request workspace",
            "Leave Management",
            {"leave_view": "requests"},
        ),
        (
            "Manage Policies",
            "Upload, review, publish, or archive policies",
            "Policies",
            {},
        ),
        (
            "Create Announcement",
            "Prepare and publish a company announcement",
            "Announcements",
            {},
        ),
    )

    for index, (title, description, page, params) in enumerate(actions):
        with st.container(
            border=True,
            key=f"admin_quick_action_card_{index}",
        ):
            st.markdown(f"**{title}**")
            st.caption(description)

            if st.button(
                f"Open {title}",
                use_container_width=True,
                key=f"admin_quick_action_button_{index}",
            ):
                _open_admin_quick_action(
                    page=page,
                    query_params=params,
                )
