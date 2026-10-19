"""Persistent operation feedback for Streamlit reruns.

Streamlit reruns immediately after successful create, edit, and delete
operations. A success message rendered before ``st.rerun()`` can disappear
too quickly. This module stores one small flash message in session state,
then displays it on the next completed page render.
"""

from typing import Literal

import streamlit as st


_FEEDBACK_STATE_KEY = "_employee_operation_feedback"


FeedbackLevel = Literal[
    "success",
    "info",
    "warning",
    "error",
]



def set_operation_feedback(
    message: str,
    *,
    level: FeedbackLevel = "success",
    namespace: str = "employee",
) -> None:
    """Store one message for the next page render."""

    normalized_message = message.strip()

    if not normalized_message:
        return

    if namespace == "employee":
        st.session_state[_FEEDBACK_STATE_KEY] = {
            "message": normalized_message,
            "level": level,
        }
        return

    state_key = f"_{namespace.strip() or 'general'}_operation_feedback"
    st.session_state[state_key] = {
        "message": normalized_message,
        "level": level,
    }


def render_operation_feedback(*, namespace: str = "employee") -> None:
    """Display and consume the most recent operation result."""

    state_key = (
        _FEEDBACK_STATE_KEY
        if namespace == "employee"
        else f"_{namespace.strip() or 'general'}_operation_feedback"
    )
    feedback = st.session_state.pop(state_key, None)

    if not isinstance(feedback, dict):
        return

    message = str(
        feedback.get("message", "")
    ).strip()
    level = str(
        feedback.get("level", "success")
    )

    if not message:
        return

    renderer = {
        "success": st.success,
        "info": st.info,
        "warning": st.warning,
        "error": st.error,
    }.get(
        level,
        st.success,
    )

    renderer(message)

    # Toast gives a short completion cue while the banner remains visible
    # in the page content for confirmation.
    if level == "success":
        st.toast(
            message,
            icon="✅",
        )
