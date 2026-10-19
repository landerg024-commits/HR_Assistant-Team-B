"""Regression tests for immediate leave-update refresh and tab retention."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE_PATH = PROJECT_ROOT / "ui/pages/admin/leave_management_page.py"


def test_credit_update_forces_fresh_widget_and_restores_account_tab() -> None:
    source = PAGE_PATH.read_text(encoding="utf-8")

    assert "_CREDIT_FORM_REVISION_PREFIX" in source
    assert 'key=f"{form_key}-value"' in source
    assert "_bump_state_revision(revision_key)" in source
    assert '"Employee Leave Accounts",\n            "Set Leave Credits"' in source


def test_rule_update_forces_fresh_database_values_and_keeps_edit_tab() -> None:
    source = PAGE_PATH.read_text(encoding="utf-8")

    assert "_LEAVE_RULE_FORM_REVISION_PREFIX" in source
    assert "saved_leave_type = LeaveService(" in source
    assert "_LEAVE_RULE_PENDING_SELECTED_ID_KEY" in source
    assert 'key=_LEAVE_RULE_SELECTED_ID_KEY' in source
    assert '"Leave Rules",\n            "Edit Leave Rule"' in source


def test_successful_updates_restore_nested_tabs_after_rerun() -> None:
    source = PAGE_PATH.read_text(encoding="utf-8")

    assert "def _activate_leave_tabs(tab_labels: list[str])" in source
    assert "targetLabels.forEach" in source
    assert "restored_tabs = st.session_state.pop" in source
    assert "if restored_tabs:" in source
    assert "elif notification_request_id is not None:" in source
