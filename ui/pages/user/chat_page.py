"""Employee HR Policy Q&A chat page."""

import streamlit as st

from authentication.current_user import AuthenticatedUser
from database.session import SessionFactory
from modules.policy_qa.policy_assistant import PolicyAssistant
from ui.components.quick_actions import render_quick_actions


CHAT_STATE_KEY = "policy_chat_messages"


def _source_lines(sources) -> list[str]:
    """Convert policy sources into chat-friendly lines."""

    lines = []

    for source in sources:
        effective_date = (
            source.effective_date.isoformat()
            if source.effective_date
            else "Not specified"
        )

        file_label = (
            source.filename
            or "Manual policy entry"
        )
        page_label = (
            f", page {source.page_number}"
            if source.page_number is not None
            else ""
        )

        lines.append(
            f"{file_label} — {source.title} — "
            f"{source.section_heading} "
            f"(v{source.version}{page_label}, "
            f"effective {effective_date})"
        )

    return lines


def render_chat_page(
    current_user: AuthenticatedUser,
) -> None:
    """Answer employee questions using approved policies only."""

    main, side = st.columns([3, 1], gap="large")

    with main:
        st.title("HR Policy Assistant")
        st.caption(
            "Answers come only from approved uploaded company policy files."
        )

        if CHAT_STATE_KEY not in st.session_state:
            st.session_state[CHAT_STATE_KEY] = [
                {
                    "role": "assistant",
                    "content": (
                        "Ask me about approved company HR policies."
                    ),
                    "sources": [],
                }
            ]

        for message in st.session_state[CHAT_STATE_KEY]:
            with st.chat_message(message["role"]):
                st.write(message["content"])

                if message.get("sources"):
                    st.markdown("**Sources**")

                    for source_line in message["sources"]:
                        st.caption(source_line)

        question = st.chat_input(
            "Ask a company policy question..."
        )

        if question:
            st.session_state[CHAT_STATE_KEY].append(
                {
                    "role": "user",
                    "content": question,
                    "sources": [],
                }
            )

            with SessionFactory() as session:
                response = PolicyAssistant(session).answer(
                    company_id=current_user.company_id,
                    question=question,
                )

            st.session_state[CHAT_STATE_KEY].append(
                {
                    "role": "assistant",
                    "content": response.answer,
                    "sources": _source_lines(
                        response.sources
                    ),
                }
            )

            st.rerun()

        st.caption(
            "Verify important concerns with HR when required."
        )

    with side:
        render_quick_actions()

        st.subheader("Policy Access")
        st.markdown(
            """
            <div class="hr-card">
                <div class="hr-title">Approved Sources Only</div>
                <div class="hr-muted">
                    Draft, archived, and future-effective policies
                    are excluded from answers.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
