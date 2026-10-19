"""Regression tests for Light Mode pages with dark form controls."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _source() -> str:
    return (
        PROJECT_ROOT
        / "ui/theme/theme_loader.py"
    ).read_text(encoding="utf-8")


def test_dark_controls_use_white_text() -> None:
    source = _source()

    assert "LIGHT PAGE + DARK FORM CONTROLS — v8.3.12" in source
    assert "background: #252630 !important" in source
    assert "color: #FFFFFF !important" in source
    assert "-webkit-text-fill-color: #FFFFFF !important" in source


def test_runtime_fallback_uses_white_text() -> None:
    source = _source()

    assert "const inputText = '#FFFFFF';" in source
    assert "const inputBackground = '#252630';" in source
    assert "const mutedText = '#B9BED0';" in source


def test_hover_and_focus_are_visible() -> None:
    source = _source()

    assert "background: #2D2F3A !important" in source
    assert "border-color: var(--hr-primary) !important" in source
    assert "box-shadow: 0 0 0 1px var(--hr-primary)" in source


def test_select_and_dropdown_values_are_white() -> None:
    source = _source()

    assert 'div[data-baseweb="select"] span' in source
    assert '[data-baseweb="popover"] [role="listbox"]' in source
    assert "background: var(--hr-primary) !important" in source


def test_labels_remain_dark_on_light_page() -> None:
    source = _source()

    assert '[data-testid="stWidgetLabel"]' in source
    assert "color: var(--hr-text-primary) !important" in source


def test_black_input_text_override_is_removed() -> None:
    source = _source()

    assert "LIGHT MODE SURFACE/TEXT CONTRAST — v8.3.11" not in source

    input_block = source.split(
        "LIGHT PAGE + DARK FORM CONTROLS — v8.3.12",
        1,
    )[1].split(
        "NATIVE STREAMLIT CONTROL HOVER — v8.3.13",
        1,
    )[0]

    assert "color: #10172A !important" not in input_block
    assert (
        "-webkit-text-fill-color: #10172A !important"
        not in input_block
    )
