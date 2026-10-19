"""First-click login regression tests."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_all_login_credentials_are_inside_one_form() -> None:
    source = _read("ui/pages/authentication/login_page.py")
    form_block = source.split(
        'with st.form(',
        1,
    )[1].split(
        'if st.button(',
        1,
    )[0]

    assert '"Company Code"' in form_block
    assert '"Username or Email"' in form_block
    assert '"Password"' in form_block
    assert "on_change=_sync_public_company_code" not in source
    assert "def _sync_public_company_code" not in source


def test_login_submit_routes_immediately() -> None:
    source = _read("authentication/session_manager.py")
    block = source.split(
        "def complete_login",
        1,
    )[1].split(
        "def flush_pending_browser_token",
        1,
    )[0]

    assert "_save_session" in block
    assert "PENDING_BROWSER_TOKEN_KEY" in block
    assert "st.rerun()" in block
    assert "write_browser_auth_token_and_continue" not in block
    assert "st.stop()" not in block


def test_browser_token_write_is_nonblocking_after_login() -> None:
    session_source = _read("authentication/session_manager.py")
    app_source = _read("app.py")
    storage_source = _read("authentication/browser_auth_storage.py")

    assert "def flush_pending_browser_token" in session_source
    assert "write_browser_auth_token(pending)" in session_source
    assert "AuthSessionManager.flush_pending_browser_token()" in app_source
    assert "def write_browser_auth_token(token: str) -> bool" in storage_source


def test_enter_and_sign_in_share_the_form_submit() -> None:
    source = _read("ui/pages/authentication/login_page.py")

    assert "st.form_submit_button(" in source
    assert '"Sign In"' in source
    assert "if submitted:" in source
