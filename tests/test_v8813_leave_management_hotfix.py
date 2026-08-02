"""Leave Management NameError and notification-filter regression tests."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _source() -> str:
    return (
        PROJECT_ROOT
        / "ui/pages/admin/leave_management_page.py"
    ).read_text(encoding="utf-8")


def test_employee_accounts_does_not_reference_request_selection() -> None:
    source = _source()
    block = source.split(
        "def _render_employee_accounts(",
        1,
    )[1].split(
        "def _render_request_details(",
        1,
    )[0]

    assert "selected_request_id" not in block


def test_request_notification_filter_reset_is_in_requests_function() -> None:
    source = _source()
    block = source.split(
        "def _render_requests(",
        1,
    )[1].split(
        "def _render_type_form(",
        1,
    )[0]

    assert "selected_request_id: int | None = None" in block
    assert "if selected_request_id is not None:" in block
    assert 'leave_request_department_{year}' in block
    assert 'leave_request_employee_search_{year}' in block
    assert "Opened from Notifications" in block


def test_all_leave_tabs_still_render_independent_functions() -> None:
    source = _source()

    assert "_render_overview(" in source
    assert "_render_employee_accounts(" in source
    assert "_render_requests(" in source
    assert "_render_rules(current_user)" in source
