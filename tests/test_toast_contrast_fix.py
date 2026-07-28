"""Regression checks for readable Streamlit toast notifications."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _source() -> str:
    return (
        PROJECT_ROOT
        / "ui/theme/theme_loader.py"
    ).read_text(encoding="utf-8")


def test_toast_surface_is_dark() -> None:
    source = _source()

    assert "TOAST CONTRAST — v8.4.2" in source
    assert '[data-testid="stToast"]' in source
    assert '[data-baseweb="toast"]' in source
    assert "background: #252630 !important" in source


def test_toast_text_is_white() -> None:
    source = _source()

    assert '[data-testid="stToast"] *' in source
    assert "color: #FFFFFF !important" in source
    assert "-webkit-text-fill-color: #FFFFFF !important" in source


def test_toast_hover_is_visible() -> None:
    source = _source()

    assert '[data-testid="stToast"]:hover' in source
    assert "background: #2D2F3A !important" in source
    assert "border-color: #565A6D !important" in source


def test_success_icon_is_green() -> None:
    source = _source()

    assert '[data-testid="stToast"] svg' in source
    assert "color: #31C77A !important" in source


def test_close_button_is_readable() -> None:
    source = _source()

    assert '[data-testid="stToast"] button' in source
    assert "color: #C7CCDA !important" in source
    assert (
        '[data-testid="stToast"] button:hover'
        in source
    )


def test_runtime_fallback_covers_late_toasts() -> None:
    source = _source()

    assert "const styleToasts = () =>" in source
    assert "styleToasts();" in source
    assert "hrToastHoverBound" in source


def test_existing_visual_fixes_remain() -> None:
    source = _source()

    assert "LIGHT PAGE + DARK FORM CONTROLS — v8.3.12" in source
    assert "NATIVE STREAMLIT CONTROL HOVER — v8.3.13" in source
    assert "TOOLTIP CONTRAST — v8.3.14" in source
    assert "DOWNLOAD ACTION CONTRAST — v8.3.15" in source
    assert "EXPANDERS — LIGHT SURFACE CONTRAST v8.4.1" in source
