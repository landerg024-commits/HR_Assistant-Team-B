"""Regression checks for fixed Light Mode UI styling."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (
        PROJECT_ROOT / relative_path
    ).read_text(encoding="utf-8")


def test_theme_toggle_is_removed_everywhere() -> None:
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


def test_light_is_the_only_supported_theme() -> None:
    assert 'SUPPORTED_THEMES = ("light",)' in _read(
        "core/constants.py"
    )
    assert 'default_theme: str = "light"' in _read(
        "config/settings.py"
    )
    assert 'DEFAULT_THEME = "light"' in _read(
        "ui/theme/theme_state.py"
    )


def test_browser_persistence_accepts_light_only() -> None:
    source = _read("ui/theme/theme_loader.py")

    assert 'const validThemes = new Set(["light"]);' in source
    assert 'new Set(["light", "dark"])' not in source


def test_inputs_use_dark_surfaces_and_white_text() -> None:
    source = _read("ui/theme/theme_loader.py")

    assert "const inputBackground = '#252630';" in source
    assert "const inputText = '#FFFFFF';" in source
    assert "const borderColor = '#3A3D4A';" in source
    assert "color-scheme: dark !important" in source
    assert "LIGHT PAGE + DARK FORM CONTROLS" in source


def test_black_input_override_is_removed() -> None:
    source = _read("ui/theme/theme_loader.py")

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


def test_input_hover_and_focus_are_dark_control_appropriate() -> None:
    source = _read("ui/theme/theme_loader.py")

    assert "background-color: #2D2F3A !important" in source
    assert "border-color: var(--hr-primary) !important" in source
    assert "box-shadow: 0 0 0 1px var(--hr-primary)" in source


def test_button_tab_and_expander_hover_are_preserved() -> None:
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
    assert "background: var(--hr-primary-soft)" in source


def test_streamlit_config_does_not_override_custom_theme() -> None:
    config_path = PROJECT_ROOT / ".streamlit/config.toml"
    assert config_path.exists()

    config = config_path.read_text(encoding="utf-8")

    assert "[client]" in config
    assert 'toolbarMode = "viewer"' in config
    assert "[theme]" not in config
    assert "primaryColor" not in config
    assert "backgroundColor" not in config
