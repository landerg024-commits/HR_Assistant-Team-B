"""Private per-account chat and topic-reset regression tests."""

from pathlib import Path

from modules.hr_assistant.hr_assistant import HRAssistant


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_chat_state_is_scoped_by_company_and_user() -> None:
    source = (
        PROJECT_ROOT
        / "ui/pages/user/chat_page.py"
    ).read_text(encoding="utf-8")

    assert "CHAT_STATE_PREFIX" in source
    assert "current_user.company_id" in source
    assert "current_user.user_id" in source
    assert "def _chat_state_key(" in source
    assert "def _chat_input_key(" in source


def test_legacy_global_chat_is_deleted_not_migrated() -> None:
    source = (
        PROJECT_ROOT
        / "ui/pages/user/chat_page.py"
    ).read_text(encoding="utf-8")

    assert "UNSCOPED_CHAT_STATE_KEYS" in source
    assert "policy_chat_messages" in source
    assert "_remove_unsafe_unscoped_chat_state()" in source
    assert "legacy =" not in source


def test_chat_input_actions_and_new_conversation_are_scoped() -> None:
    source = (
        PROJECT_ROOT
        / "ui/pages/user/chat_page.py"
    ).read_text(encoding="utf-8")

    assert "key=chat_input_key" in source
    assert "new_hr_assistant_conversation__" in source
    assert "hr_assistant_action_" in source
    assert "_chat_identity(current_user)" in source


def test_auth_clears_private_chat_on_user_change_and_logout() -> None:
    source = (
        PROJECT_ROOT
        / "authentication/session_manager.py"
    ).read_text(encoding="utf-8")

    assert "HR_CHAT_STATE_PREFIXES" in source
    assert "def _clear_hr_assistant_browser_state(" in source
    assert "previous_identity != current_identity" in source

    logout_block = source.split(
        "def logout(cls) -> None:",
        1,
    )[1].split(
        "def clear_after_password_reset",
        1,
    )[0]

    assert "_clear_hr_assistant_browser_state()" in logout_block


def test_policy_starts_new_topic_after_leave() -> None:
    history = [
        {
            "role": "user",
            "content": "How do I file leave?",
        },
        {
            "role": "assistant",
            "content": "Open Leave Management.",
            "intent": "file_leave",
        },
    ]

    assert HRAssistant.classify_intent(
        "policy",
        history=history,
    ) == "policy"


def test_benefits_and_documents_start_new_topics_after_leave() -> None:
    history = [
        {
            "role": "user",
            "content": "Ilan VL ko?",
        },
        {
            "role": "assistant",
            "content": "Your VL balance.",
            "intent": "leave_balance",
        },
    ]

    assert HRAssistant.classify_intent(
        "benefits",
        history=history,
    ) == "benefits"
    assert HRAssistant.classify_intent(
        "my documents",
        history=history,
    ) == "documents"


def test_explicit_ambiguous_follow_up_keeps_leave_context() -> None:
    history = [
        {
            "role": "user",
            "content": "Paano mag-file ng VL?",
        },
        {
            "role": "assistant",
            "content": "Open Leave Management.",
            "intent": "file_leave",
        },
    ]

    assert HRAssistant.classify_intent(
        "Ilan na lang?",
        history=history,
    ) == "leave_balance"


def test_short_new_topic_is_not_automatically_follow_up() -> None:
    history = [
        {
            "role": "user",
            "content": "Ilan VL ko?",
        },
        {
            "role": "assistant",
            "content": "Your VL balance.",
            "intent": "leave_balance",
        },
    ]

    assert HRAssistant._contextual_query(
        "policy",
        history,
    ) == "policy"
    assert HRAssistant._contextual_query(
        "documents",
        history,
    ) == "documents"


def test_plain_leave_starts_fresh_leave_overview() -> None:
    assert HRAssistant.classify_intent(
        "leave"
    ) == "leave_overview"
