"""Initial administrator dashboard shell."""

import streamlit as st

from authentication.current_user import AuthenticatedUser


def render_admin_dashboard_page(
    current_user: AuthenticatedUser,
) -> None:
    """Display safe account status and future module placeholders."""

    st.title("Admin Dashboard")
    st.caption("Secure administration access is active.")

    metric_columns = st.columns(4)
    metrics = (
        ("Company", current_user.company_code),
        ("Role", current_user.role_name),
        ("Account", current_user.username),
        ("Password Status", "Updated"),
    )

    for column, (label, value) in zip(
        metric_columns,
        metrics,
    ):
        with column:
            st.metric(label, value)

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown(
        """
        <div class="hr-placeholder">
            <strong>Administration Foundation Ready</strong><br><br>
            User management, employee management, policies, leave settings,
            reports, and audits remain modular placeholders.
        </div>
        """,
        unsafe_allow_html=True,
    )
