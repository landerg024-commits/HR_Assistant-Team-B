"""Read, write, and remove the signed authentication browser cookie.

The previous implementation asked a sandboxed Streamlit component iframe
to navigate the top-level page. Some browsers block that navigation, which
left login stuck on "Completing sign in..." and logout stuck with only the
sidebar visible.

Corrected transition:

1. Render the cookie writer/remover component.
2. Wait briefly so the browser can commit the cookie operation.
3. Use a native Streamlit fragment timer to rerun the full application.

No iframe top-level navigation is used.
"""

from time import monotonic

import streamlit as st

from config.settings import get_settings


AUTH_COOKIE_NAME = "ai_hr_signed_auth"
COOKIE_CONTROLLER_KEY = "ai_hr_auth_cookie_controller"
TRANSITION_STARTED_KEY = "_auth_cookie_transition_started"
TRANSITION_KIND_KEY = "_auth_cookie_transition_kind"


def read_auth_cookie() -> str | None:
    """Read the signed cookie from the current browser request."""

    value = st.context.cookies.get(AUTH_COOKIE_NAME)

    if not isinstance(value, str) or not value.strip():
        return None

    return value.strip()


def _get_cookie_controller():
    """Load the cookie writer component only when needed."""

    try:
        from streamlit_cookies_controller import (
            CookieController,
        )
    except ImportError as error:
        raise RuntimeError(
            "streamlit-cookies-controller is not installed. "
            "Run: python -m pip install -r requirements.txt"
        ) from error

    return CookieController(
        key=COOKIE_CONTROLLER_KEY
    )


def _wait_then_rerun(
    *,
    transition_kind: str,
    message: str,
) -> None:
    """Wait for the cookie component and then rerun the full app."""

    if (
        st.session_state.get(TRANSITION_KIND_KEY)
        != transition_kind
    ):
        st.session_state[TRANSITION_KIND_KEY] = (
            transition_kind
        )
        st.session_state[TRANSITION_STARTED_KEY] = (
            monotonic()
        )

    st.info(message)

    @st.fragment(run_every="1s")
    def transition_timer() -> None:
        """Perform one full app rerun after the commit delay."""

        started_at = float(
            st.session_state.get(
                TRANSITION_STARTED_KEY,
                monotonic(),
            )
        )

        if monotonic() - started_at >= 0.9:
            st.session_state.pop(
                TRANSITION_STARTED_KEY,
                None,
            )
            st.session_state.pop(
                TRANSITION_KIND_KEY,
                None,
            )

            # Full app rerun, not fragment-only rerun.
            st.rerun(scope="app")

    transition_timer()

    # The rendered fragment remains active after execution stops.
    st.stop()


def write_auth_cookie_and_continue(
    token: str,
) -> None:
    """Write the login cookie and continue to the correct portal."""

    settings = get_settings()
    controller = _get_cookie_controller()

    controller.set(
        AUTH_COOKIE_NAME,
        token,
        path="/",
        max_age=settings.auth_cookie_hours * 60 * 60,
        secure=settings.auth_cookie_secure,
        same_site="strict",
    )

    _wait_then_rerun(
        transition_kind="login",
        message="Completing sign in…",
    )


def replace_auth_cookie_and_continue(
    token: str,
) -> None:
    """Replace the cookie after password change and continue."""

    settings = get_settings()
    controller = _get_cookie_controller()

    controller.set(
        AUTH_COOKIE_NAME,
        token,
        path="/",
        max_age=settings.auth_cookie_hours * 60 * 60,
        secure=settings.auth_cookie_secure,
        same_site="strict",
    )

    st.success("Password changed successfully.")

    _wait_then_rerun(
        transition_kind="password_change",
        message="Opening your portal…",
    )


def remove_auth_cookie(
    *,
    wait_for_completion: bool,
) -> None:
    """Remove the signed authentication cookie."""

    controller = _get_cookie_controller()
    settings = get_settings()

    try:
        controller.remove(
            AUTH_COOKIE_NAME,
            path="/",
            secure=settings.auth_cookie_secure,
            same_site="strict",
        )
    except KeyError:
        # The browser request may contain the cookie even when the
        # component's local cache does not. The remove command was sent
        # before the local dictionary lookup raised the error.
        pass

    if wait_for_completion:
        _wait_then_rerun(
            transition_kind="logout",
            message="Signing out…",
        )
