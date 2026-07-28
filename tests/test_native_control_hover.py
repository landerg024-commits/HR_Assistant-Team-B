"""Regression checks for native Streamlit control hover styles."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _source() -> str:
    return (
        PROJECT_ROOT
        / "ui/theme/theme_loader.py"
    ).read_text(encoding="utf-8")


def test_file_uploader_dropzone_has_hover() -> None:
    source = _source()

    assert "NATIVE STREAMLIT CONTROL HOVER — v8.3.13" in source
    assert '[data-testid="stFileUploaderDropzone"]:hover' in source
    assert "background: #2D2F3A !important" in source
    assert "border-color: var(--hr-primary) !important" in source


def test_file_uploader_button_has_visible_hover() -> None:
    source = _source()

    assert (
        '[data-testid="stFileUploaderDropzone"] button:hover'
        in source
    )
    assert "background: var(--hr-primary) !important" in source
    assert "color: #FFFFFF !important" in source


def test_uploaded_file_row_has_hover() -> None:
    source = _source()

    assert '[data-testid="stFileUploaderFile"]:hover' in source
    assert '[data-testid="stFileUploaderFileData"]:hover' in source


def test_remove_file_button_has_danger_hover() -> None:
    source = _source()

    assert '[data-testid="stFileUploaderDeleteBtn"] button:hover' in source
    assert "background: #E05252 !important" in source


def test_checkbox_has_light_page_hover() -> None:
    source = _source()

    assert '[data-testid="stCheckbox"] label:hover' in source
    assert "background: var(--hr-primary-soft) !important" in source
    assert "color: var(--hr-primary) !important" in source


def test_dark_input_and_white_text_rules_are_preserved() -> None:
    source = _source()

    assert "LIGHT PAGE + DARK FORM CONTROLS — v8.3.12" in source
    assert "background: #252630 !important" in source
    assert "-webkit-text-fill-color: #FFFFFF !important" in source
