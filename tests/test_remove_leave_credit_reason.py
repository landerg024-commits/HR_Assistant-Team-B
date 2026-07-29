"""Regression checks for the simplified leave-credit form."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_leave_credit_form_contains_only_required_controls() -> None:
    source = (
        PROJECT_ROOT
        / "ui/pages/admin/leave_management_page.py"
    ).read_text(encoding="utf-8")

    editor = source.split(
        "def _render_credit_balance_editor(",
        1,
    )[1].split(
        "def _credit_history_entry(",
        1,
    )[0]

    assert '"Leave Type"' in editor
    assert '"New Leave Credits"' in editor
    assert '"Save Leave Credits"' in editor
    assert "Reason for Change" not in editor
    assert "Adjustment Reason" not in editor


def test_history_note_contains_balances_only() -> None:
    source = (
        PROJECT_ROOT
        / "services/leave_service.py"
    ).read_text(encoding="utf-8")

    method = source.split(
        "def set_credit_balance(",
        1,
    )[1].split(
        "def list_credit_history(",
        1,
    )[0]

    assert "Previous balance:" in method
    assert "New balance:" in method
    assert 'f"{values.reason}' not in method
