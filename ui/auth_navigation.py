"""Query-parameter navigation for public authentication pages."""

from typing import Any

import streamlit as st


AUTH_ACTION_KEY = "auth"
RESET_TOKEN_KEY = "token"
PUBLIC_COMPANY_KEY = "company"
VALID_AUTH_ACTIONS = {
    "forgot",
    "reset",
}


def _clean_value(
    value: Any,
    *,
    max_length: int,
) -> str | None:
    """Return one bounded string query value."""

    if isinstance(value, (list, tuple)):
        value = value[0] if value else None

    if not isinstance(value, str):
        return None

    cleaned = value.strip()

    if not cleaned or len(cleaned) > max_length:
        return None

    return cleaned


def get_auth_action() -> str | None:
    """Return a supported public auth action."""

    action = _clean_value(
        st.query_params.get(AUTH_ACTION_KEY),
        max_length=20,
    )

    return (
        action
        if action in VALID_AUTH_ACTIONS
        else None
    )


def get_public_company_code() -> str | None:
    """Return a bounded company code used only for public branding."""

    value = _clean_value(
        st.query_params.get(
            PUBLIC_COMPANY_KEY
        ),
        max_length=50,
    )

    return value.upper() if value else None


def get_reset_token() -> str:
    """Return the raw token supplied by the email reset URL."""

    return (
        _clean_value(
            st.query_params.get(RESET_TOKEN_KEY),
            max_length=512,
        )
        or ""
    )


def open_forgot_password() -> None:
    """Open the public forgot-password page."""

    for key in (
        "portal",
        "page",
        RESET_TOKEN_KEY,
    ):
        if key in st.query_params:
            del st.query_params[key]

    st.query_params[AUTH_ACTION_KEY] = "forgot"
    st.rerun()


def return_to_login() -> None:
    """Remove public auth routing and show login."""

    for key in (
        AUTH_ACTION_KEY,
        RESET_TOKEN_KEY,
        "portal",
        "page",
    ):
        if key in st.query_params:
            del st.query_params[key]

    st.rerun()
