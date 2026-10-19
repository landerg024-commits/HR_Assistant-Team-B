"""Static checks for Light Mode BaseWeb select styling."""

from pathlib import Path


THEME_LOADER = (
    Path(__file__).resolve().parents[1]
    / "ui"
    / "theme"
    / "theme_loader.py"
)


def _source() -> str:
    return THEME_LOADER.read_text(encoding="utf-8")


def test_generic_baseweb_select_is_styled() -> None:
    source = _source()

    assert 'div[data-baseweb="select"]' in source
    assert '[role="combobox"]' in source
    assert '[aria-selected]' in source


def test_select_values_use_white_text_on_dark() -> None:
    source = _source()

    assert 'div[data-baseweb="select"] span' in source
    assert 'div[data-baseweb="select"] p' in source
    assert "-webkit-text-fill-color: #FFFFFF" in source
    assert "background-color: #252630" in source


def test_runtime_handler_queries_baseweb_directly() -> None:
    source = _source()

    assert (
        ".querySelectorAll(\n"
        "                        '[data-baseweb=\"select\"]'"
        in source
    )
    assert ".querySelectorAll('*')" in source
