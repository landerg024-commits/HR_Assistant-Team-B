"""Static regression checks for Light Mode page with dark form-widget styling."""

from pathlib import Path


THEME_LOADER = (
    Path(__file__).resolve().parents[1]
    / "ui"
    / "theme"
    / "theme_loader.py"
)


def _theme_source() -> str:
    return THEME_LOADER.read_text(encoding="utf-8")


def test_date_input_is_covered_by_light_override() -> None:
    source = _theme_source()

    assert '[data-testid="stDateInput"] input' in source
    assert '[data-testid="stDateInput"] button svg' in source


def test_selectbox_is_covered_by_light_override() -> None:
    source = _theme_source()

    assert 'div[data-baseweb="select"]' in source
    assert 'div[data-baseweb="select"] span' in source
    assert 'div[data-baseweb="select"] [role="combobox"]' in source


def test_runtime_enforcer_handles_date_and_select_widgets() -> None:
    source = _theme_source()

    assert '[data-testid="stDateInput"] input' in source
    assert '[data-baseweb="select"]' in source
    assert "styleSelectBoxes" in source
    assert "styleEditableFields" in source
