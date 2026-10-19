"""Static integration checks for Forgot Password pages."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (
        PROJECT_ROOT / relative_path
    ).read_text(encoding="utf-8")


def test_login_has_forgot_password_action() -> None:
    source = _read(
        "ui/pages/authentication/login_page.py"
    )

    assert '"Forgot Password?"' in source
    assert "open_forgot_password()" in source


def test_app_routes_public_forgot_and_reset_pages() -> None:
    source = _read("app.py")

    assert 'auth_action == "forgot"' in source
    assert 'auth_action == "reset"' in source
    assert "render_forgot_password_layout" in source
    assert "render_reset_password_layout" in source


def test_public_request_uses_generic_message() -> None:
    source = _read(
        "authentication/password_reset_service.py"
    )

    assert "GENERIC_RESET_REQUEST_MESSAGE" in source
    assert "raw reset tokens are never stored" in source.lower()


def test_reset_page_does_not_request_old_password() -> None:
    source = _read(
        "ui/pages/authentication/reset_password_page.py"
    )

    assert '"New Password"' in source
    assert '"Confirm New Password"' in source
    assert '"Current Password"' not in source


def test_admin_fallback_never_displays_existing_password() -> None:
    source = _read(
        "ui/pages/admin/users_page.py"
    )

    assert "Administrator-Assisted Password Reset" in source
    assert "existing password is never displayed" in source
    assert '"Set Temporary Password"' in source


def test_authenticated_sessions_are_revalidated() -> None:
    source = _read(
        "authentication/session_manager.py"
    )

    assert "Revalidation means a password reset" in source
    assert "restore_user(token)" in source
