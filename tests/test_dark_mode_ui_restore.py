"""Regression checks for minimal Dark Mode enforcement."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (
        PROJECT_ROOT / relative_path
    ).read_text(encoding="utf-8")


def test_theme_toggle_is_removed_from_all_sidebars() -> None:
    assert not (
        PROJECT_ROOT
        / "ui/components/theme_toggle.py"
    ).exists()

    for relative_path in [
        "ui/components/auth_sidebar.py",
        "ui/components/admin_sidebar.py",
        "ui/components/sidebar.py",
    ]:
        source = _read(relative_path)

        assert "render_theme_toggle" not in source
        assert "theme_toggle" not in source


def test_dark_is_the_only_supported_theme() -> None:
    constants = _read("core/constants.py")
    settings = _read("config/settings.py")
    state = _read("ui/theme/theme_state.py")

    assert 'SUPPORTED_THEMES = ("dark",)' in constants
    assert 'default_theme: str = "dark"' in settings
    assert 'DEFAULT_THEME = "dark"' in state


def test_stable_input_contrast_code_is_preserved() -> None:
    source = _read("ui/theme/theme_loader.py")

    assert "def _enforce_input_value_contrast()" in source
    assert "const inputBackground = '#252630';" in source
    assert "const inputText = '#FFFFFF';" in source
    assert "MutationObserver" in source
    assert "UNIVERSAL FORM CONTROL VALUE CONTRAST" in source


def test_stable_design_tokens_are_not_replaced() -> None:
    source = _read("ui/theme/design_tokens.py")

    # Both original dictionaries remain so the stable file structure and
    # every previous CSS token stay untouched.
    assert "LIGHT_THEME" in source
    assert "DARK_THEME" in source
    assert '"surface": "#171D2C"' in source
    assert '"primary_soft": "#292852"' in source


def test_no_native_streamlit_theme_override_was_added() -> None:
    # The corrective patch must not add a new native theme file because
    # that was one source of widget appearance changes in v8.3.8.
    assert not (
        PROJECT_ROOT
        / ".streamlit/config.toml"
    ).exists()


def test_browser_sync_accepts_dark_only_without_css_changes() -> None:
    source = _read("ui/theme/theme_loader.py")

    assert 'const validThemes = new Set(["dark"]);' in source
    assert "_synchronize_theme_with_browser" in source


def test_hover_restore_remains_present() -> None:
    source = _read("ui/theme/theme_loader.py")

    assert (
        "div.stButton > button:not(:disabled):hover"
        in source
    )
    assert (
        '[data-testid="stTabs"] button[role="tab"]:hover'
        in source
    )
    assert (
        '[data-testid="stExpander"] details > summary:hover'
        in source
    )
