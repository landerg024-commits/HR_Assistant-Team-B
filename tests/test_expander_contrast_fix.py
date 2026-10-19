"""Regression checks for visible Streamlit expander headers."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _source() -> str:
    return (
        PROJECT_ROOT
        / "ui/theme/theme_loader.py"
    ).read_text(encoding="utf-8")


def test_expander_normal_state_is_visible_without_hover() -> None:
    source = _source()

    assert "EXPANDERS — LIGHT SURFACE CONTRAST v8.4.1" in source
    assert '[data-testid="stExpander"] details > summary' in source
    assert "background: #FFFFFF !important" in source
    assert "color: #10172A !important" in source
    assert "-webkit-text-fill-color: #10172A !important" in source


def test_nested_expander_label_is_forced_visible() -> None:
    source = _source()

    assert (
        '[data-testid="stExpander"] details > summary *'
        in source
    )
    assert "opacity: 1 !important" in source
    assert "text-shadow: none !important" in source


def test_expander_hover_matches_light_ui() -> None:
    source = _source()

    assert (
        '[data-testid="stExpander"] details > summary:hover'
        in source
    )
    assert "background: var(--hr-primary-soft) !important" in source
    assert "color: var(--hr-primary-text) !important" in source


def test_expanded_state_remains_visible_after_hover() -> None:
    source = _source()

    assert (
        '[data-testid="stExpander"] details[open] > summary'
        in source
    )
    assert "background: var(--hr-primary-soft) !important" in source
    assert (
        '[data-testid="stExpander"] '
        'details[open] > summary *'
        in source
    )


def test_expander_arrow_is_visible() -> None:
    source = _source()

    assert (
        '[data-testid="stExpander"] '
        'details > summary svg'
        in source
    )
    assert "color: #68738C !important" in source


def test_policy_preview_still_uses_expander() -> None:
    source = (
        PROJECT_ROOT
        / "ui/pages/admin/policies_page.py"
    ).read_text(encoding="utf-8")

    assert (
        'with st.expander("Document Preview", expanded=True):'
        in source
    )


def test_previous_light_ui_fixes_remain() -> None:
    source = _source()

    assert "LIGHT PAGE + DARK FORM CONTROLS — v8.3.12" in source
    assert "NATIVE STREAMLIT CONTROL HOVER — v8.3.13" in source
    assert "TOOLTIP CONTRAST — v8.3.14" in source
    assert "DOWNLOAD ACTION CONTRAST — v8.3.15" in source
