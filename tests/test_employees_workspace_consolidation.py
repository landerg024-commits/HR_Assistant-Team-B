"""Navigation tests for the single Employee Master Record page."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (
        PROJECT_ROOT / relative_path
    ).read_text(encoding="utf-8")


def test_sidebar_contains_only_employees_item() -> None:
    source = _read("ui/components/admin_sidebar.py")
    navigation = source.split(
        "ADMIN_NAVIGATION =",
        1,
    )[1].split(
        "def render_admin_sidebar",
        1,
    )[0]

    assert '"Employees"' in navigation
    assert '"Users"' not in navigation
    assert '"Roles"' not in navigation


def test_employee_master_tabs_replace_user_role_tabs() -> None:
    source = _read(
        "ui/pages/admin/employees_page.py"
    )

    assert '"Employee List"' in source
    assert '"Add Employee"' in source
    assert '"Edit Employee"' in source
    assert "render_users_page" not in source
    assert "render_roles_page" not in source


def test_admin_router_has_one_employee_route() -> None:
    source = _read("ui/layouts/admin_layout.py")

    assert 'elif page == "Employees":' in source
    assert 'page in {' not in source
