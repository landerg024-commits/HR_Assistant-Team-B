"""Static integration checks for leave routing and notification bell."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_admin_navigation_uses_leave_management() -> None:
    source = (ROOT / "ui/components/admin_sidebar.py").read_text(encoding="utf-8")
    assert '"Leave Management"' in source
    assert '"Leave Settings"' not in source
    layout = (ROOT / "ui/layouts/admin_layout.py").read_text(encoding="utf-8")
    assert "render_admin_leave_management_page" in layout


def test_employee_leave_page_is_routed() -> None:
    source = (ROOT / "ui/layouts/user_layout.py").read_text(encoding="utf-8")
    assert "render_employee_leave_management_page" in source
    assert '{"Leave Management", "My Requests"}' in source


def test_notification_bell_has_unread_count_and_mark_read() -> None:
    source = (ROOT / "ui/components/topbar.py").read_text(encoding="utf-8")
    assert 'label = f"🔔 {unread}"' in source
    assert '"Mark All as Read"' in source
    assert "NotificationService" in source


def test_leave_request_email_supports_cc_and_attachment() -> None:
    source = (ROOT / "integrations/email/email_sender.py").read_text(encoding="utf-8")
    assert "class EmailAttachment" in source
    assert "cc_emails: tuple[str, ...]" in source
    assert "email_message.add_attachment" in source


def test_new_leave_tables_are_registered() -> None:
    source = (ROOT / "models/__init__.py").read_text(encoding="utf-8")
    for model in ["LeaveType", "LeaveBalance", "LeaveRequest", "LeaveCreditTransaction", "Notification"]:
        assert model in source
