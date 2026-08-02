"""Specific notification deep-link regression tests."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_leave_notification_sets_request_and_view_context() -> None:
    source = (
        ROOT / "ui/components/topbar.py"
    ).read_text(encoding="utf-8")

    assert '"leave_request_id"' in source
    assert '"leave_view"' in source
    assert "def _leave_notification_view(" in source
    assert 'return "pending"' in source
    assert 'return "reviewed"' in source
    assert 'return "requests"' in source
    assert 'st.query_params["leave_view"]' in source


def test_admin_notification_selects_request_inside_leave_requests_tab() -> None:
    source = (
        ROOT / "ui/pages/admin/leave_management_page.py"
    ).read_text(encoding="utf-8")

    assert "def _notification_leave_request_id(" in source
    assert "selected_request_id: int | None = None" in source
    assert '_activate_leave_tab("Leave Requests")' in source
    assert "st.session_state[selector_key] = selected_request_id" in source
    assert "Leave Requests / Specific Request" not in source
    assert "Back to All Leave Requests" not in source


def test_employee_own_request_deep_link_selects_exact_request() -> None:
    source = (
        ROOT / "ui/pages/user/leave_management_page.py"
    ).read_text(encoding="utf-8")

    assert "selected_request_id: int | None = None" in source
    assert "option_ids.index(" in source
    assert "inside the My Requests tab" in source
    assert "_activate_employee_leave_tab(target_label)" in source


def test_manager_notifications_route_to_pending_or_reviewed() -> None:
    source = (
        ROOT / "ui/pages/user/leave_management_page.py"
    ).read_text(encoding="utf-8")

    assert '"pending": "Pending Approvals"' in source
    assert '"reviewed": "Reviewed Requests"' in source
    assert "_render_pending_approvals(" in source
    assert "_render_reviewed_requests(" in source
    assert "def _render_reviewed_request_detail(" in source


def test_direct_view_accepts_notification_specific_sections() -> None:
    source = (
        ROOT / "ui/pages/user/leave_management_page.py"
    ).read_text(encoding="utf-8")

    helper = source.split(
        "def _assistant_leave_view(",
        1,
    )[1].split(
        "def _notification_leave_request_id(",
        1,
    )[0]

    assert '"pending"' in helper
    assert '"reviewed"' in helper
    assert '"requests"' in helper
