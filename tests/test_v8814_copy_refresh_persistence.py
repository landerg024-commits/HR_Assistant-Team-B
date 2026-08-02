"""Native copy and deterministic browser-refresh authentication tests."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_streamlit_developer_cache_tools_are_hidden() -> None:
    config = _read(".streamlit/config.toml")

    assert "[client]" in config
    assert 'toolbarMode = "viewer"' in config


def test_copy_guard_preserves_native_copy() -> None:
    source = _read("ui/theme/theme_loader.py")
    block = source.split("def _install_native_copy_shortcut_guard", 1)[1]

    assert "event.stopImmediatePropagation();" in block
    assert "event.preventDefault()" not in block
    assert '(event.ctrlKey || event.metaKey)' in block
    assert 'key === "c"' in block


def test_cookie_component_is_not_refreshed_twice() -> None:
    source = _read("authentication/browser_auth_cookie.py")

    assert "controller.refresh()" not in source
    assert "component_auth_cookie" in source
    assert "controller.get(" in source


def test_refresh_waits_for_first_component_result() -> None:
    source = _read("authentication/session_manager.py")

    assert "cookie_component_was_mounted()" in source
    assert "component_auth_cookie()" in source
    assert "wait_for_initial_cookie_component()" in source
    assert "COOKIE_RESTORE_MAX_ATTEMPTS" not in source


def test_login_allows_cookie_command_to_commit() -> None:
    source = _read("authentication/browser_auth_cookie.py")

    assert "def _delayed_app_rerun" in source
    assert 'transition_kind="login"' in source
    assert "read_auth_cookie" not in source
    assert "controller.refresh()" not in source


def test_logout_uses_same_safe_transition() -> None:
    source = _read("authentication/browser_auth_cookie.py")

    assert 'transition_kind="logout"' in source
    assert "controller.remove(" in source
    assert "wait_for_completion" in source
