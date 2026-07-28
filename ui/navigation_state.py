"""Persist the last portal and page in safe URL query parameters.

Navigation labels are not authentication credentials. They are restored
only after cookie authentication succeeds, and administrator access is
still checked by AccessControl before an admin page is rendered.
"""

from typing import Any



PORTAL_QUERY_KEY = "portal"
PAGE_QUERY_KEY = "page"
VALID_PORTALS = {"admin", "employee"}


def _clean_query_value(
    value: Any,
    *,
    max_length: int,
) -> str | None:
    """Return a small printable query value or None."""

    if isinstance(value, (list, tuple)):
        value = value[0] if value else None

    if not isinstance(value, str):
        return None

    cleaned = value.strip()

    if not cleaned or len(cleaned) > max_length:
        return None

    return cleaned


def initialize_navigation_state() -> None:
    """Restore portal/page values for a new Streamlit browser session."""

    import streamlit as st

    query_portal = _clean_query_value(
        st.query_params.get(PORTAL_QUERY_KEY),
        max_length=20,
    )
    query_page = _clean_query_value(
        st.query_params.get(PAGE_QUERY_KEY),
        max_length=100,
    )

    if "portal_mode" not in st.session_state:
        st.session_state.portal_mode = (
            query_portal
            if query_portal in VALID_PORTALS
            else "employee"
        )

    if "current_page" not in st.session_state:
        st.session_state.current_page = (
            query_page or "Chat Assistant"
        )


def set_navigation_state(
    *,
    portal_mode: str,
    current_page: str,
) -> None:
    """Update both session state and refresh-safe URL navigation."""

    import streamlit as st

    normalized_portal = (
        portal_mode
        if portal_mode in VALID_PORTALS
        else "employee"
    )
    normalized_page = (
        current_page.strip()[:100]
        if current_page.strip()
        else "Chat Assistant"
    )

    st.session_state.portal_mode = normalized_portal
    st.session_state.current_page = normalized_page

    if (
        st.query_params.get(PORTAL_QUERY_KEY)
        != normalized_portal
    ):
        st.query_params[PORTAL_QUERY_KEY] = normalized_portal

    if (
        st.query_params.get(PAGE_QUERY_KEY)
        != normalized_page
    ):
        st.query_params[PAGE_QUERY_KEY] = normalized_page


def clear_navigation_state() -> None:
    """Remove only navigation parameters while preserving theme state."""

    import streamlit as st

    for key in (PORTAL_QUERY_KEY, PAGE_QUERY_KEY):
        if key in st.query_params:
            del st.query_params[key]

    st.session_state.portal_mode = "employee"
    st.session_state.current_page = "Chat Assistant"
