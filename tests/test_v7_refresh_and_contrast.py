"""Static checks for refresh login and universal form contrast."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (
        PROJECT_ROOT / relative_path
    ).read_text(encoding="utf-8")


def test_login_uses_bundled_browser_storage_component() -> None:
    login_source = _read(
        "ui/pages/authentication/login_page.py"
    )
    storage_source = _read(
        "authentication/browser_auth_storage.py"
    )

    assert "complete_login(" in login_source
    assert "declare_component" in storage_source
    assert "read_browser_auth_token" in storage_source
    assert "write_browser_auth_token" in storage_source


def test_third_party_cookie_dependency_is_removed() -> None:
    requirements = _read("requirements.txt")

    assert "streamlit-cookies-controller" not in requirements


def test_all_form_control_types_have_dark_control_override() -> None:
    source = _read("ui/theme/theme_loader.py")

    assert "LIGHT PAGE + DARK FORM CONTROLS — v8.3.12" in source
    assert 'div[data-baseweb="select"]' in source
    assert '[role="combobox"]' in source
    assert 'input:not([type="checkbox"])' in source
    assert "styleEditableFields" in source
    assert "styleSelectBoxes" in source
    assert "const inputBackground = '#252630';" in source
    assert "const inputText = '#FFFFFF';" in source
