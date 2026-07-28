"""Static checks for employee-only portal UI and route guards."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (
        PROJECT_ROOT / relative_path
    ).read_text(encoding="utf-8")


def test_employee_sidebar_hides_admin_button_for_employee() -> None:
    """Admin Portal button must remain inside the admin-role condition."""

    source = _read("ui/components/sidebar.py")

    condition_position = source.index(
        "if AccessControl.is_admin(current_user):"
    )
    button_position = source.index(
        '"Admin Portal"',
        condition_position,
    )

    assert button_position > condition_position


def test_app_blocks_admin_portal_for_non_admin_user() -> None:
    """Changing the URL must not bypass role authorization."""

    source = _read("app.py")

    assert (
        'portal_mode == "admin"'
        in source
    )
    assert (
        "not AccessControl.is_admin(current_user)"
        in source
    )
    assert (
        'st.session_state.portal_mode = "employee"'
        in source
    )
    assert (
        'st.session_state.current_page = "Chat Assistant"'
        in source
    )


def test_admin_layout_has_defense_in_depth() -> None:
    """Admin layout must independently require administrator access."""

    source = _read("ui/layouts/admin_layout.py")

    assert "AccessControl.require_admin(current_user)" in source
