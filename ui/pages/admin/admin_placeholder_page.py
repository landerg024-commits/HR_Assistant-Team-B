"""Consistent placeholder for future administrator modules."""

import streamlit as st


def render_admin_placeholder_page(page_name: str) -> None:
    """Show the selected admin module's development status."""

    st.title(page_name)

    st.markdown(
        f"""
        <div class="hr-placeholder">
            <strong>{page_name}</strong><br><br>
            Authentication and access control are active.
            This administration process will be implemented
            in its assigned development module.
        </div>
        """,
        unsafe_allow_html=True,
    )
