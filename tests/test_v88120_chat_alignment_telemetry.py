"""Chat layout, input contrast, and current local vector-store regression checks."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _source(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_user_questions_are_right_aligned_in_both_shared_chat_views() -> None:
    theme = _source("ui/theme/theme_loader.py")
    admin = _source("ui/pages/admin/chat_page.py")
    employee = _source("ui/pages/user/chat_page.py")

    assert '[data-testid="stChatMessageAvatarUser"]' in theme
    assert "margin-left: auto !important;" in theme
    assert "flex-direction: row-reverse !important;" in theme
    assert "st.chat_message(role)" in admin
    assert "st.chat_message(role)" in employee


def test_chat_input_has_dark_surface_and_white_text() -> None:
    theme = _source("ui/theme/theme_loader.py")

    assert '[data-testid="stChatInput"] textarea' in theme
    assert "background-color: #252630 !important;" in theme
    assert "-webkit-text-fill-color: #FFFFFF !important;" in theme
    assert "textarea::placeholder" in theme


def test_qdrant_persistent_local_vector_store_is_configured() -> None:
    smart_ai = _source("modules/smart_ai/portal_ai.py")
    env_example = _source(".env.example")

    assert "from qdrant_client import QdrantClient" in smart_ai
    assert "QdrantClient(" in smart_ai
    assert "path=path" in smart_ai
    assert "SMART_AI_QDRANT_DIR=data/smart_ai/qdrant" in env_example
    assert "SMART_AI_QDRANT_COLLECTION=hr_portal_knowledge" in env_example


def test_v88120_release_remains_preserved_after_later_checkpoints() -> None:
    settings = _source("config/settings.py")
    readme = _source("README.md")

    assert 'app_version: str = "0.8.8.' in settings
    assert "v8.8.221 — Qdrant Vector Database Migration" in readme
