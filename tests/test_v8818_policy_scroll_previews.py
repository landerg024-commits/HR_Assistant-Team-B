"""Regression checks for bounded full policy previews and editor."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _policy_source() -> str:
    return (
        PROJECT_ROOT / "ui/pages/admin/policies_page.py"
    ).read_text(encoding="utf-8")


def _theme_source() -> str:
    return (
        PROJECT_ROOT / "ui/theme/theme_loader.py"
    ).read_text(encoding="utf-8")


def test_upload_headings_and_text_are_bounded_but_complete() -> None:
    source = _policy_source()
    theme = _theme_source()

    assert "hr-policy-headings-scroll" in source
    assert "complete list" in source
    assert "Scroll inside the preview box" in source
    assert "max-height: 170px !important" in theme
    assert "max-height: 420px !important" in theme
    assert "overflow-y: scroll !important" in theme
    assert "maximum_sections" not in source


def test_manage_preview_keeps_complete_text_inside_viewer() -> None:
    source = _policy_source()

    extracted = source.split(
        "def _render_extracted_content(", 1
    )[1].split("def _render_sections(", 1)[0]

    assert "value=text" in extracted
    assert "height=POLICY_CONTENT_VIEWER_HEIGHT" in extracted
    assert "shown = text[:" not in extracted
    assert "Download Complete Extracted Text" in extracted


def test_manage_edit_uses_fixed_height_scroll_editor() -> None:
    source = _policy_source()

    editor = source.split(
        '"Editable Policy Content *"', 1
    )[1].split("submitted = st.form_submit_button(", 1)[0]

    assert "height=POLICY_CONTENT_EDITOR_HEIGHT" in editor
    assert "Scroll inside the editor" in editor
    assert "_full_content_editor_height" not in source
