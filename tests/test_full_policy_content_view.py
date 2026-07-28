"""Regression checks for complete policy content display."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _policy_source() -> str:
    return (
        PROJECT_ROOT
        / "ui/pages/admin/policies_page.py"
    ).read_text(encoding="utf-8")


def _theme_source() -> str:
    return (
        PROJECT_ROOT
        / "ui/theme/theme_loader.py"
    ).read_text(encoding="utf-8")


def test_no_upload_preview_truncation_remains() -> None:
    source = _policy_source()

    forbidden = [
        "MAX_PREVIEW_CHARACTERS",
        "maximum_characters",
        "maximum_sections",
        "Preview limited",
        "more detected section",
        "[:MAX_PREVIEW",
    ]

    for value in forbidden:
        assert value not in source


def test_all_unique_headings_are_collected() -> None:
    source = _policy_source()

    helper = source.split(
        "def _unique_preview_headings(",
        1,
    )[1].split(
        "def _render_detected_headings(",
        1,
    )[0]

    assert "limit" not in helper
    assert "break" not in helper
    assert "headings.append(heading)" in helper


def test_preview_uses_full_section_html_blocks() -> None:
    source = _policy_source()

    assert "hr-policy-section-preview" in source
    assert "hr-policy-preview-section" in source
    assert "hr-policy-preview-heading" in source
    assert "hr-policy-preview-content" in source
    assert "html.escape(value)" in source
    assert '.replace("\\n", "<br>")' in source


def test_policy_editor_has_no_fixed_height() -> None:
    source = _policy_source()

    editor_block = source.split(
        '"Editable Policy Content *"',
        1,
    )[1].split(
        "submitted = st.form_submit_button(",
        1,
    )[0]

    assert "height=520" not in editor_block
    assert "_full_content_editor_height(" in editor_block


def test_textarea_line_spacing_is_compact() -> None:
    source = _theme_source()

    assert "POLICY TEXT READABILITY — v8.4.6" in source
    assert "line-height: 1.30 !important" in source
    assert "font-size: 0.90rem !important" in source
    assert "padding: 12px 14px !important" in source


def test_full_preview_is_used_in_both_upload_flows() -> None:
    source = _policy_source()

    # Definition plus main upload and Upload New Version calls.
    assert source.count(
        "_render_full_section_preview("
    ) == 3
