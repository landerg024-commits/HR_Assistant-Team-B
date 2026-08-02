"""Refresh-safe signed authentication regression tests."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_refresh_reads_request_cookie_before_component() -> None:
    source = (
        PROJECT_ROOT / "authentication/session_manager.py"
    ).read_text(encoding="utf-8")
    block = source.split("def restore_from_cookie", 1)[1].split(
        "def complete_password_change", 1
    )[0]

    assert "request_auth_cookie()" in block
    assert "component_auth_cookie()" in block
    assert block.index("request_auth_cookie()") < block.index(
        "component_auth_cookie()"
    )


def test_first_cookie_component_result_is_awaited() -> None:
    source = (
        PROJECT_ROOT / "authentication/session_manager.py"
    ).read_text(encoding="utf-8")

    assert "cookie_component_was_mounted()" in source
    assert "wait_for_initial_cookie_component()" in source
    assert "COOKIE_RESTORE_ATTEMPT_KEY" not in source
    assert "COOKIE_RESTORE_CHECKED_KEY" not in source


def test_cookie_signing_secret_remains_persistent() -> None:
    source = (
        PROJECT_ROOT / "authentication/signed_cookie_auth_service.py"
    ).read_text(encoding="utf-8")

    assert "resolve_auth_cookie_secret" in source
    assert "_load_or_create_local_secret" in source
    assert "auth_cookie_secret_file" in source


def test_admin_and_employee_share_one_restore_flow() -> None:
    source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")

    assert "AuthSessionManager.restore_from_cookie()" in source
    assert "render_admin_layout" in source
    assert "render_user_layout" in source
