"""Notification button and anchored dropdown regression tests."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_notification_uses_anchored_dropdown_not_dialog() -> None:
    source = (
        PROJECT_ROOT
        / "ui/components/topbar.py"
    ).read_text(encoding="utf-8")

    assert 'key="global_notification_button"' in source
    assert 'type="primary"' in source
    assert 'key="notification_dropdown_panel"' in source
    assert 'key="notification_menu_wrapper"' in source
    assert '@st.dialog("Notifications")' not in source
    assert "st.popover(" not in source


def test_notification_count_is_visible_before_click() -> None:
    source = (
        PROJECT_ROOT
        / "ui/components/topbar.py"
    ).read_text(encoding="utf-8")

    assert 'f"🔔 {unread}"' in source
    assert "_global_notification_panel_open" in source


def test_notification_dropdown_is_positioned_under_bell() -> None:
    source = (
        PROJECT_ROOT
        / "ui/theme/theme_loader.py"
    ).read_text(encoding="utf-8")

    block = source.split(
        "ANCHORED NOTIFICATION DROPDOWN — v8.7.6",
        1,
    )[1]

    assert "position: absolute !important;" in block
    assert "top: calc(100% + 8px) !important;" in block
    assert "right: 0 !important;" in block
    assert "z-index: 10030 !important;" in block


def test_notification_button_follows_company_color() -> None:
    source = (
        PROJECT_ROOT
        / "ui/theme/theme_loader.py"
    ).read_text(encoding="utf-8")

    block = source.split(
        "ANCHORED NOTIFICATION DROPDOWN — v8.7.6",
        1,
    )[1]

    assert "background: var(--hr-primary) !important;" in block
    assert "color: var(--hr-on-primary) !important;" in block


def test_notification_cards_and_mark_all_remain_available() -> None:
    source = (
        PROJECT_ROOT
        / "ui/components/topbar.py"
    ).read_text(encoding="utf-8")

    assert "_notification_button_label(item)" in source
    assert '"Mark All as Read"' in source
    assert '"Close"' in source
