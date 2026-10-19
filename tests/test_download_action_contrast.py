"""Regression checks for Streamlit download-action contrast."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _source() -> str:
    return (
        PROJECT_ROOT
        / "ui/theme/theme_loader.py"
    ).read_text(encoding="utf-8")


def test_download_normal_state_is_readable() -> None:
    source = _source()

    assert "DOWNLOAD ACTION CONTRAST — v8.3.15" in source
    assert '[data-testid="stDownloadButton"] > a' in source
    assert "background: #FFFFFF !important" in source
    assert "color: #10172A !important" in source


def test_download_hover_is_violet_with_white_text() -> None:
    source = _source()

    assert '[data-testid="stDownloadButton"] > a:hover' in source
    assert "background: var(--hr-primary) !important" in source
    assert "color: #FFFFFF !important" in source


def test_download_focus_active_and_disabled_are_explicit() -> None:
    source = _source()

    assert (
        '[data-testid="stDownloadButton"] > a:focus-visible'
        in source
    )
    assert "0 0 0 3px rgba(var(--hr-primary-rgb), 0.22)" in source
    assert '[data-testid="stDownloadButton"] > a:active' in source
    assert "background: var(--hr-primary-hover) !important" in source
    assert 'a[aria-disabled="true"]' in source
    assert "background: #EEF1F6 !important" in source


def test_runtime_fallback_covers_dynamic_download_markup() -> None:
    source = _source()

    assert "const styleDownloadButtons = () =>" in source
    assert "styleDownloadButtons();" in source
    assert "hrDownloadHoverBound" in source


def test_previous_visual_fixes_remain() -> None:
    source = _source()

    assert "LIGHT PAGE + DARK FORM CONTROLS — v8.3.12" in source
    assert "NATIVE STREAMLIT CONTROL HOVER — v8.3.13" in source
    assert "TOOLTIP CONTRAST — v8.3.14" in source
