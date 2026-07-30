"""Employee context-aware HR Assistant chat page."""

import streamlit as st

from authentication.current_user import AuthenticatedUser
from database.session import SessionFactory
from modules.hr_assistant.hr_assistant import HRAssistant
from ui.components.quick_actions import render_quick_actions
from ui.navigation_state import set_navigation_state


CHAT_STATE_PREFIX = "hr_assistant_chat_messages__"
CHAT_INPUT_PREFIX = "hr_assistant_chat_input__"
UNSCOPED_CHAT_STATE_KEYS = {
    "hr_assistant_chat_messages",
    "policy_chat_messages",
}
_ACTION_QUERY_KEYS = {
    "leave_view",
    "announcement_id",
    "leave_request_id",
    "policy_id",
}


def _chat_identity(
    current_user: AuthenticatedUser,
) -> str:
    """Return the company-and-user identity for private browser state."""

    return (
        f"company_{current_user.company_id}"
        f"__user_{current_user.user_id}"
    )


def _chat_state_key(
    current_user: AuthenticatedUser,
) -> str:
    """Return the signed-in account's private conversation key."""

    return (
        f"{CHAT_STATE_PREFIX}"
        f"{_chat_identity(current_user)}"
    )


def _chat_input_key(
    current_user: AuthenticatedUser,
) -> str:
    """Return the signed-in account's private chat-input key."""

    return (
        f"{CHAT_INPUT_PREFIX}"
        f"{_chat_identity(current_user)}"
    )


def _remove_unsafe_unscoped_chat_state() -> None:
    """Delete chat values made by older non-private builds."""

    for key in UNSCOPED_CHAT_STATE_KEYS:
        st.session_state.pop(
            key,
            None,
        )


def _source_lines(sources) -> list[str]:
    """Convert approved policy sources into chat-friendly lines."""

    lines = []

    for source in sources:
        effective_date = (
            source.effective_date.isoformat()
            if source.effective_date
            else "Not specified"
        )
        file_label = source.filename or "Manual policy entry"
        page_label = (
            f", page {source.page_number}"
            if source.page_number is not None
            else ""
        )

        lines.append(
            f"{file_label} — {source.title} — {source.section_heading} "
            f"(v{source.version}{page_label}, effective {effective_date})"
        )

    return lines


def _open_action(action: dict) -> None:
    """Navigate to one assistant-recommended employee module."""

    for key in _ACTION_QUERY_KEYS:
        if key in st.query_params:
            del st.query_params[key]

    set_navigation_state(
        portal_mode=str(action.get("portal_mode", "employee")),
        current_page=str(action.get("page", "Dashboard")),
    )

    for key, value in dict(action.get("query_params", {})).items():
        st.query_params[str(key)] = str(value)

    st.rerun()


def _render_message_actions(
    *,
    current_user: AuthenticatedUser,
    message_index: int,
    actions: list[dict],
) -> None:
    """Render clickable navigation buttons below one assistant answer."""

    if not actions:
        return

    st.markdown("**Open related HR page**")

    for action_index, action in enumerate(actions):
        if st.button(
            str(action.get("label", "Open")),
            use_container_width=True,
            key=(
                "hr_assistant_action_"
                f"{_chat_identity(current_user)}_"
                f"{message_index}_{action_index}"
            ),
        ):
            _open_action(action)


def _initial_messages() -> list[dict]:
    """Return the grounded welcome message for a new conversation."""

    return [
        {
            "role": "assistant",
            "content": (
                "Ask me about leave credits, filing leave, request status, "
                "your employee information, approved HR policies, documents, "
                "benefits, onboarding, announcements, or HR contacts. You may "
                "use shorthand such as VL, SL, or EL."
            ),
            "sources": [],
            "actions": [],
            "intent": "welcome",
        }
    ]


def render_chat_page(current_user: AuthenticatedUser) -> None:
    """Answer HR questions using live records and approved policies."""

    main, side = st.columns([3, 1], gap="large")

    with main:
        st.title("HR Assistant")
        st.caption(
            "Uses your live HR records, configured HR modules, and approved "
            "company policies. It does not guess."
        )

        _remove_unsafe_unscoped_chat_state()

        chat_state_key = _chat_state_key(
            current_user
        )
        chat_input_key = _chat_input_key(
            current_user
        )

        if chat_state_key not in st.session_state:
            st.session_state[
                chat_state_key
            ] = _initial_messages()

        messages = st.session_state[
            chat_state_key
        ]

        for message_index, message in enumerate(messages):
            role = str(message.get("role", "assistant"))
            message_key = (
                "hr_assistant_message_"
                f"{_chat_identity(current_user)}_"
                f"{role}_{message_index}"
            )

            with st.chat_message(role):
                # Stable wrapper for Light Mode contrast and Markdown lists.
                with st.container(key=message_key):
                    st.markdown(
                        str(message.get("content", ""))
                    )

                    if message.get("sources"):
                        st.markdown(
                            "**Approved policy sources**"
                        )
                        for source_line in message["sources"]:
                            st.caption(source_line)

                    _render_message_actions(
                        current_user=current_user,
                        message_index=message_index,
                        actions=message.get("actions", []),
                    )

        question = st.chat_input(
            "Ask an HR question, e.g. 'Ilan na lang VL ko?'",
            key=chat_input_key,
        )

        if question:
            previous_history = list(messages)
            messages.append(
                {
                    "role": "user",
                    "content": question,
                    "sources": [],
                    "actions": [],
                }
            )

            with SessionFactory() as session:
                response = HRAssistant(session).answer(
                    current_user=current_user,
                    question=question,
                    history=previous_history,
                )

            messages.append(
                {
                    "role": "assistant",
                    "content": response.answer,
                    "sources": _source_lines(response.sources),
                    "actions": [
                        {
                            "label": action.label,
                            "page": action.page,
                            "portal_mode": action.portal_mode,
                            "query_params": dict(action.query_params),
                        }
                        for action in response.actions
                    ],
                    "intent": response.intent,
                }
            )
            st.rerun()

        st.caption(
            "Verify sensitive or exceptional cases with HR when required."
        )

    with side:
        if st.button(
            "New HR Conversation",
            use_container_width=True,
            key=(
                "new_hr_assistant_conversation__"
                f"{_chat_identity(current_user)}"
            ),
        ):
            st.session_state[
                _chat_state_key(current_user)
            ] = _initial_messages()
            st.session_state.pop(
                _chat_input_key(current_user),
                None,
            )
            st.rerun()

        render_quick_actions()

        st.subheader("Answer Sources")
        st.markdown(
            """
            <div class="hr-card">
                <div class="hr-title">Live Data + Approved Policies</div>
                <div class="hr-muted">
                    Personal balances and requests come from live company
                    records. Policy answers come only from published and
                    currently effective policy files.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
