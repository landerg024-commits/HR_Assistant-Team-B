"""Fixed Light Mode state management.

Persistence layers:
1. Streamlit session_state keeps the theme during widget reruns.
2. The ``theme`` URL query parameter survives browser refreshes.
3. Browser localStorage, synchronized by theme_loader.py, restores the
   last selection when a completely new Streamlit session starts.

Streamlit is imported lazily inside runtime functions so the pure theme
normalization helpers can be unit-tested without a Streamlit runtime.
"""

from typing import Any

from core.constants import SUPPORTED_THEMES


THEME_QUERY_KEY = "theme"
DEFAULT_THEME = "light"


def normalize_theme(value: Any) -> str | None:
    """Return a supported lowercase theme or None.

    Query parameters may be a string or a one-item sequence depending on
    the Streamlit/browser environment, so both forms are supported.
    """

    if isinstance(value, (list, tuple)):
        value = value[0] if value else None

    if not isinstance(value, str):
        return None

    normalized = value.strip().lower()

    return (
        normalized
        if normalized in SUPPORTED_THEMES
        else None
    )


def resolve_initial_theme(
    query_theme: Any,
    default_theme: Any,
) -> str:
    """Choose a supported theme; Light Mode is the only valid result."""

    return (
        normalize_theme(query_theme)
        or normalize_theme(default_theme)
        or DEFAULT_THEME
    )


def initialize_theme_state(default_theme: str) -> None:
    """Initialize or restore the active Streamlit theme.

    A valid URL query value has priority because it represents the saved
    browser state after a refresh. When no query value exists, the app
    uses its configured default temporarily; browser localStorage can then
    restore a previous selection through theme_loader.py.
    """

    import streamlit as st

    query_theme = normalize_theme(
        st.query_params.get(THEME_QUERY_KEY)
    )

    if query_theme is not None:
        # This also corrects an existing session when the URL changes.
        st.session_state.theme = query_theme
        return

    if "theme" not in st.session_state:
        st.session_state.theme = resolve_initial_theme(
            query_theme=None,
            default_theme=default_theme,
        )


def get_active_theme() -> str:
    """Return a guaranteed supported theme for rendering."""

    import streamlit as st

    return (
        normalize_theme(st.session_state.get("theme"))
        or DEFAULT_THEME
    )


def set_active_theme(theme: str) -> str:
    """Persist the supported Light Mode value for compatibility."""

    import streamlit as st

    normalized = normalize_theme(theme)

    if normalized is None:
        raise ValueError(
            f"Unsupported theme: {theme!r}. "
            f"Allowed values: {', '.join(SUPPORTED_THEMES)}."
        )

    st.session_state.theme = normalized
    st.query_params[THEME_QUERY_KEY] = normalized

    return normalized
