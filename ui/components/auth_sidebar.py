"""Branding sidebar displayed before protected navigation is available."""

import streamlit as st



def render_auth_sidebar(
    assistant_name: str,
    company_name: str,
) -> None:
    """Display login branding and support text."""

    st.sidebar.markdown(
        f"<div class='hr-brand'>🤖 {assistant_name}</div>",
        unsafe_allow_html=True,
    )
    st.sidebar.caption(company_name)
    st.sidebar.divider()

    st.sidebar.markdown(
        """
        <div class="hr-card" style="min-height: auto;">
            <div class="hr-card-title">Secure HR Access</div>
            <div class="hr-card-text">
                Sign in using your company code and assigned account.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.sidebar.divider()

    st.sidebar.markdown(
        """
        <div class="hr-muted" style="margin-top: 18px;">
            Use Forgot Password when you can access your registered Login Email. Otherwise, contact your HR administrator.
        </div>
        """,
        unsafe_allow_html=True,
    )
