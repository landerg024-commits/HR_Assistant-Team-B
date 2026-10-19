"""Checks for grouped policy headings, content, and white text."""

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


def test_separator_precedes_heading_and_content() -> None:
    source = _policy_source()

    formatter = source.split(
        "def _format_section_preview(",
        1,
    )[1].split(
        "def _policy_text_to_html(",
        1,
    )[0]

    separator_position = formatter.index("'─' * 56")
    heading_position = formatter.index("{index}. {heading}")
    body_position = formatter.index("{body}")

    assert separator_position < heading_position < body_position


def test_heading_and_body_share_one_section() -> None:
    source = _policy_source()

    renderer = source.split(
        "def _render_full_section_preview(",
        1,
    )[1].split(
        "def _format_size(",
        1,
    )[0]

    assert (
        "<section class='hr-policy-preview-section'>"
        in renderer
    )
    assert (
        "<div class='hr-policy-preview-heading'>"
        in renderer
    )
    assert (
        "<div class='hr-policy-preview-content'>"
        in renderer
    )
    assert renderer.index("safe_heading") < renderer.index(
        "safe_body"
    )


def test_source_lines_use_explicit_html_breaks() -> None:
    source = _policy_source()

    assert "def _policy_text_to_html(" in source
    assert "html.escape(value)" in source
    assert '.replace("\\n", "<br>")' in source


def test_all_nested_preview_text_is_white() -> None:
    source = _theme_source()

    assert (
        "POLICY SECTION HEADING/CONTENT LAYOUT — v8.4.7"
        in source
    )
    assert ".hr-policy-preview-heading" in source
    assert ".hr-policy-preview-content" in source
    assert "color: #FFFFFF !important" in source
    assert (
        "-webkit-text-fill-color: #FFFFFF !important"
        in source
    )


def test_section_spacing_is_compact() -> None:
    source = _theme_source()

    assert "padding: 8px 0 9px 0 !important" in source
    assert "margin: 0 0 4px 0 !important" in source
    assert "line-height: 1.24 !important" in source
    assert "line-height: 1.26 !important" in source


def test_final_separator_is_present() -> None:
    policy_source = _policy_source()
    theme_source = _theme_source()

    assert "hr-policy-preview-final-line" in policy_source
    assert ".hr-policy-preview-final-line" in theme_source
    assert (
        "border-top: 1px solid #666B7C !important"
        in theme_source
    )


def test_full_unlimited_preview_remains() -> None:
    source = _policy_source()

    assert "MAX_PREVIEW_CHARACTERS" not in source
    assert "Preview limited" not in source
    assert "more detected section" not in source
    assert source.count(
        "_render_full_section_preview("
    ) == 4
