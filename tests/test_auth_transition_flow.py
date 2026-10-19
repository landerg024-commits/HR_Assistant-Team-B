"""Static checks for non-blocking login and logout transitions."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (
        PROJECT_ROOT / relative_path
    ).read_text(encoding="utf-8")


def test_transition_messages_exist() -> None:
    source = _read(
        "authentication/browser_auth_cookie.py"
    )

    assert "Completing sign in…" in source
    assert "Signing out…" in source
    assert "Opening your portal…" in source


def test_logout_blocks_stale_cookie_restore() -> None:
    source = _read(
        "authentication/session_manager.py"
    )

    assert "LOGOUT_PENDING_KEY" in source
    assert (
        "if st.session_state.get(cls.LOGOUT_PENDING_KEY)"
        in source
    )


def test_logout_waits_for_cookie_removal() -> None:
    source = _read(
        "authentication/session_manager.py"
    )

    assert "wait_for_completion=True" in source
