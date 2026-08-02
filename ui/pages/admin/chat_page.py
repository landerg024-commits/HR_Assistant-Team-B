"""Private context-aware HR Assistant page for administrators."""

import streamlit as st

from authentication.access_control import AccessControl
from authentication.current_user import AuthenticatedUser
from database.session import SessionFactory
from modules.hr_assistant.admin_hr_assistant import AdminHRAssistant
from ui.components.quick_actions import render_admin_quick_actions
from ui.navigation_state import set_navigation_state


ADMIN_CHAT_STATE_PREFIX = "admin_hr_assistant_chat_messages__"
ADMIN_CHAT_INPUT_PREFIX = "admin_hr_assistant_chat_input__"
_ADMIN_ACTION_QUERY_KEYS = {
    "announcement_id",
    "employee_id",
    "leave_request_id",
    "leave_view",
    "policy_id",
}


def _admin_chat_identity(current_user: AuthenticatedUser) -> str:
    """Return company-and-user identity for private admin chat state."""

    return (
        f"company_{current_user.company_id}"
        f"__user_{current_user.user_id}"
    )


def _admin_chat_state_key(current_user: AuthenticatedUser) -> str:
    return (
        f"{ADMIN_CHAT_STATE_PREFIX}"
        f"{_admin_chat_identity(current_user)}"
    )


def _admin_chat_input_key(current_user: AuthenticatedUser) -> str:
    return (
        f"{ADMIN_CHAT_INPUT_PREFIX}"
        f"{_admin_chat_identity(current_user)}"
    )


def _source_lines(sources) -> list[str]:
    """Convert approved-policy source objects into readable lines."""

    lines = []
    for source in sources:
        effective_date = (
            source.effective_date.isoformat()
            if source.effective_date
            else "Not specified"
        )
        filename = source.filename or "Manual policy entry"
        page = (
            f", page {source.page_number}"
            if source.page_number is not None
            else ""
        )
        lines.append(
            f"{filename} — {source.title} — {source.section_heading} "
            f"(v{source.version}{page}, effective {effective_date})"
        )
    return lines


def _open_admin_action(action: dict) -> None:
    """Navigate safely to an assistant-recommended portal page."""

    for key in _ADMIN_ACTION_QUERY_KEYS:
        if key in st.query_params:
            del st.query_params[key]

    set_navigation_state(
        portal_mode=str(action.get("portal_mode", "admin")),
        current_page=str(action.get("page", "Admin Dashboard")),
    )

    for key, value in dict(action.get("query_params", {})).items():
        st.query_params[str(key)] = str(value)

    st.rerun()


def _render_actions(
    *,
    current_user: AuthenticatedUser,
    message_index: int,
    actions: list[dict],
) -> None:
    if not actions:
        return

    st.markdown("**Open related admin page**")
    for action_index, action in enumerate(actions):
        if st.button(
            str(action.get("label", "Open")),
            use_container_width=True,
            key=(
                "admin_hr_assistant_action_"
                f"{_admin_chat_identity(current_user)}_"
                f"{message_index}_{action_index}"
            ),
        ):
            _open_admin_action(action)


def _initial_messages() -> list[dict]:
    return [
        {
            "role": "assistant",
            "content": (
                "Ask me about company employees, user accounts, leave requests, "
                "leave credits, policies, announcements, integrations, company "
                "settings, or your own employee information."
            ),
            "sources": [],
            "actions": [],
            "intent": "welcome",
        }
    ]


def render_admin_chat_page(current_user: AuthenticatedUser) -> None:
    """Render the private company-scoped administrator assistant."""

    AccessControl.require_admin(current_user)

    main, side = st.columns([3, 1], gap="large")

    with main:
        st.title("Admin HR Assistant")
        st.caption(
            "Uses live company-scoped HR data and approved policies. "
            "Restricted security secrets are never displayed."
        )

        chat_state_key = _admin_chat_state_key(current_user)
        chat_input_key = _admin_chat_input_key(current_user)

        if chat_state_key not in st.session_state:
            st.session_state[chat_state_key] = _initial_messages()

        messages = st.session_state[chat_state_key]

        for message_index, message in enumerate(messages):
            role = str(message.get("role", "assistant"))
            message_key = (
                "hr_assistant_message_admin_"
                f"{_admin_chat_identity(current_user)}_"
                f"{role}_{message_index}"
            )

            with st.chat_message(role):
                with st.container(key=message_key):
                    st.markdown(str(message.get("content", "")))

                    if message.get("sources"):
                        st.markdown("**Approved policy sources**")
                        for source_line in message["sources"]:
                            st.caption(source_line)

                    _render_actions(
                        current_user=current_user,
                        message_index=message_index,
                        actions=message.get("actions", []),
                    )

        question = st.chat_input(
            "Ask an admin HR question, e.g. 'How many employees do we have?'",
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
                response = AdminHRAssistant(session).answer(
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
            "Company-wide results are restricted to the authenticated company."
        )

    with side:
        if st.button(
            "New Admin Conversation",
            use_container_width=True,
            key=(
                "new_admin_hr_assistant_conversation__"
                f"{_admin_chat_identity(current_user)}"
            ),
        ):
            st.session_state[chat_state_key] = _initial_messages()
            st.session_state.pop(chat_input_key, None)
            st.rerun()

        render_admin_quick_actions()
