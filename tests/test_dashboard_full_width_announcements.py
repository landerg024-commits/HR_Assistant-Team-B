"""Employee dashboard full-width announcement regression tests."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_removes_redundant_quick_access() -> None:
    source = (
        PROJECT_ROOT / "ui/pages/user/dashboard_page.py"
    ).read_text(encoding="utf-8")

    assert "Quick Access" not in source
    assert "_render_quick_access" not in source
    assert "_open_employee_page" not in source
    assert "quick_access_area" not in source
    assert "announcement_area" not in source


def test_dashboard_uses_full_width_announcements() -> None:
    source = (
        PROJECT_ROOT / "ui/pages/user/dashboard_page.py"
    ).read_text(encoding="utf-8")

    assert 'st.markdown("## Company Announcements")' in source
    assert "[1.0, 2.0]" in source
    assert "dashboard_announcement_category" in source
    assert "dashboard_announcement_search" in source
    assert "Featured" in source
    assert "Latest Updates" in source


def test_notification_deep_link_is_preserved() -> None:
    source = (
        PROJECT_ROOT / "ui/pages/user/dashboard_page.py"
    ).read_text(encoding="utf-8")

    assert "def _target_announcement_id(" in source
    assert '"announcement_id"' in source
    assert "Opened from Notifications" in source
