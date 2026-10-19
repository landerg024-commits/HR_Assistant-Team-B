"""Transparent larger sidebar company-logo sizing regression tests."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_logo_uses_larger_transparent_holder() -> None:
    source = (
        PROJECT_ROOT / "ui/theme/theme_loader.py"
    ).read_text(encoding="utf-8")
    block = source.split(
        "COMPANY LOGO — v8.8.7",
        1,
    )[1]

    assert "height: 132px" in block
    assert "padding: 0;" in block
    assert "background: transparent;" in block
    assert "border: none;" in block
    assert "box-shadow: none;" in block
    assert "width: 100% !important" in block
    assert "height: 100% !important" in block
    assert "max-height: 128px !important" in block
    assert "object-fit: contain !important" in block
    assert "object-position: center !important" in block
