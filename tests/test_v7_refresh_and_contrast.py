"""Static checks for refresh login and universal form contrast."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (
        PROJECT_ROOT / relative_path
    ).read_text(encoding="utf-8")


def test_login_uses_cookie_component_then_streamlit_rerun() -> None:
    login_source = _read(
        "ui/pages/authentication/login_page.py"
    )
    cookie_source = _read(
        "authentication/browser_auth_cookie.py"
    )

    assert "complete_login(" in login_source
    assert "CookieController" in cookie_source
    assert '@st.fragment(run_every="1s")' in cookie_source
    assert 'st.rerun(scope="app")' in cookie_source
    assert "location.replace" not in cookie_source
    assert "parentWindow.location" not in cookie_source


def test_cookie_controller_dependency_is_present() -> None:
    requirements = _read("requirements.txt")

    assert (
        "streamlit-cookies-controller==0.0.4"
        in requirements
    )


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
