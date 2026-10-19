"""Root-cause regression tests for native Copy and refresh auth."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_copy_guard_stops_streamlit_listener_without_preventing_copy() -> None:
    source = (ROOT / "ui/theme/theme_loader.py").read_text(encoding="utf-8")
    block = source.split("def _install_native_copy_shortcut_guard", 1)[1]

    assert "event.stopImmediatePropagation();" in block
    assert "event.preventDefault()" not in block
    assert 'key === "c"' in block
    assert 'parentWindow.addEventListener(' in block
    assert "_install_native_copy_shortcut_guard()" in source


def test_cookie_reader_never_refreshes_same_component_in_one_run() -> None:
    source = (ROOT / "authentication/browser_auth_cookie.py").read_text(
        encoding="utf-8"
    )

    assert "controller.refresh()" not in source
    assert "component_auth_cookie" in source
    assert "cookie_component_was_mounted" in source
    assert "wait_for_initial_cookie_component" in source


def test_restore_mounts_component_once_before_showing_login() -> None:
    source = (ROOT / "authentication/session_manager.py").read_text(
        encoding="utf-8"
    )
    block = source.split("def restore_from_cookie", 1)[1].split(
        "def complete_password_change", 1
    )[0]

    assert "request_auth_cookie()" in block
    assert "was_mounted = cookie_component_was_mounted()" in block
    assert "token = component_auth_cookie()" in block
    assert "wait_for_initial_cookie_component()" in block
    assert "COOKIE_RESTORE_MAX_ATTEMPTS" not in source


def test_cookie_transition_does_not_re_read_component() -> None:
    source = (ROOT / "authentication/browser_auth_cookie.py").read_text(
        encoding="utf-8"
    )
    block = source.split("def _delayed_app_rerun", 1)[1].split(
        "def write_auth_cookie_and_continue", 1
    )[0]

    assert "read_auth_cookie" not in block
    assert "component_auth_cookie" not in block
    assert "st.rerun(scope=\"app\")" in block
