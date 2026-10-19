"""Regression checks for readable Streamlit help tooltips."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _source() -> str:
    return (
        PROJECT_ROOT
        / "ui/theme/theme_loader.py"
    ).read_text(encoding="utf-8")


def test_tooltip_surface_is_dark() -> None:
    source = _source()

    assert "TOOLTIP CONTRAST — v8.3.14" in source
    assert '[role="tooltip"]' in source
    assert '[data-baseweb="tooltip"]' in source
    assert "background: #252630 !important" in source


def test_tooltip_text_is_white() -> None:
    source = _source()

    assert '[role="tooltip"] *' in source
    assert "color: #FFFFFF !important" in source
    assert "-webkit-text-fill-color: #FFFFFF !important" in source


def test_tooltip_icon_has_visible_hover() -> None:
    source = _source()

    assert '[data-testid="stTooltipIcon"]:hover' in source
    assert "background: var(--hr-primary-soft) !important" in source
    assert "color: var(--hr-primary) !important" in source


def test_runtime_fallback_styles_late_tooltips() -> None:
    source = _source()

    assert "const styleTooltips = () =>" in source
    assert "styleTooltips();" in source
    assert "'[role=\"tooltip\"]'" in source
    assert "'#FFFFFF'" in source


def test_existing_uploader_hover_is_preserved() -> None:
    source = _source()

    assert "NATIVE STREAMLIT CONTROL HOVER — v8.3.13" in source
    assert '[data-testid="stFileUploaderDropzone"]:hover' in source
    assert (
        '[data-testid="stFileUploaderDropzone"] button:hover'
        in source
    )


def test_light_page_dark_input_rules_are_preserved() -> None:
    source = _source()

    assert "LIGHT PAGE + DARK FORM CONTROLS — v8.3.12" in source
    assert "const inputText = '#FFFFFF';" in source
    assert "const inputBackground = '#252630';" in source
