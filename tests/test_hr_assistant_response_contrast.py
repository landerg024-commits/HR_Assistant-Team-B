"""HR Assistant and read-only Markdown contrast tests."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _theme_source() -> str:
    return (
        PROJECT_ROOT
        / "ui/theme/theme_loader.py"
    ).read_text(encoding="utf-8")


def test_chat_uses_keyed_markdown_message_wrapper() -> None:
    source = (
        PROJECT_ROOT
        / "ui/pages/user/chat_page.py"
    ).read_text(encoding="utf-8")

    assert "hr_assistant_message_" in source
    assert "key=message_key" in source
    assert "st.markdown(" in source
    assert 'st.write(message["content"])' not in source


def test_chat_lists_and_emphasis_use_light_mode_text() -> None:
    source = _theme_source()
    block = source.split(
        "READ-ONLY CONTENT CONTRAST — v8.8.1",
        1,
    )[1]

    assert 'class*="st-key-hr_assistant_message_"' in block
    assert '[data-testid="stMarkdownContainer"] li' in block
    assert "color: var(--hr-text-primary) !important;" in block
    assert (
        "-webkit-text-fill-color: "
        "var(--hr-text-primary) !important;"
        in block
    )


def test_other_read_only_lists_are_included() -> None:
    source = _theme_source()
    block = source.split(
        "READ-ONLY CONTENT CONTRAST — v8.8.1",
        1,
    )[1]

    assert '[data-testid="stMain"]' in block
    assert '[data-testid="stExpander"]' in block
    assert '[data-testid="stAlert"]' in block


def test_runtime_reapplies_content_contrast_after_rerender() -> None:
    source = _theme_source()

    assert "const styleReadableContent = () =>" in source
    assert "styleReadableContent();" in source
    assert (
        '.replace("__TEXT_PRIMARY__", tokens["text_primary"])'
        in source
    )


def test_runtime_targets_read_only_containers_not_form_widgets() -> None:
    source = _theme_source()
    function = source.split(
        "const styleReadableContent = () =>",
        1,
    )[1].split(
        "let frameRequested = false;",
        1,
    )[0]

    assert "stMarkdownContainer" in function
    assert "stChatMessage" in function
    assert "stExpander" in function
    assert "stAlert" in function
    assert "stTextInput" not in function
    assert "stTextArea" not in function
    assert "role=\"textbox\"" not in function
