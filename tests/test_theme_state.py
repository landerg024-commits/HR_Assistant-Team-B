"""Pure tests for fixed Light Mode theme resolution."""

from ui.theme.theme_state import (
    normalize_theme,
    resolve_initial_theme,
)


def test_normalize_theme_accepts_light() -> None:
    assert normalize_theme("LIGHT") == "light"
    assert normalize_theme(["light"]) == "light"


def test_dark_and_invalid_themes_are_rejected() -> None:
    assert normalize_theme("dark") is None
    assert normalize_theme("blue") is None
    assert normalize_theme(None) is None


def test_initial_theme_resolves_to_light() -> None:
    assert (
        resolve_initial_theme(
            query_theme="dark",
            default_theme="light",
        )
        == "light"
    )
    assert (
        resolve_initial_theme(
            query_theme=None,
            default_theme="light",
        )
        == "light"
    )
    assert (
        resolve_initial_theme(
            query_theme="invalid",
            default_theme="invalid",
        )
        == "light"
    )
