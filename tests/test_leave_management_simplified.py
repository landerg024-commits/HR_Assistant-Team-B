"""Static regression checks for the simplified Leave Management UI."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _source() -> str:
    return (
        PROJECT_ROOT
        / "ui/pages/admin/leave_management_page.py"
    ).read_text(encoding="utf-8")


def test_overview_does_not_duplicate_full_employee_credit_view() -> None:
    source = _source()

    overview = source.split(
        "def _render_overview(",
        1,
    )[1].split(
        "def _render_employee_account_summary(",
        1,
    )[0]

    assert "_render_credit_breakdown(" not in overview
    assert "_render_credit_balance_editor(" not in overview
    assert "_render_credit_history(" not in overview


def test_employee_account_has_department_and_employee_selector() -> None:
    source = _source()

    accounts = source.split(
        "def _render_employee_accounts(",
        1,
    )[1].split(
        "def _filtered_requests(",
        1,
    )[0]

    assert '"Department"' in accounts
    assert '"Employee"' in accounts
    assert '"All Departments"' in accounts
    assert "_render_employee_account_summary(" in accounts
    assert "_render_credit_breakdown(" in accounts


def test_overview_has_low_credit_and_recent_request_sections() -> None:
    source = _source()

    assert "def _low_credit_rows(" in source
    assert "_LOW_CREDIT_THRESHOLD" in source
    assert "Attention Needed" in source
    assert "Recent Leave Requests" in source


def test_leave_rules_have_clear_action_names() -> None:
    source = _source()

    assert '"Add Leave Rule"' in source
    assert '"Edit Leave Rule"' in source
    assert '"Save Leave Rule"' in source
    assert "Handover Plan" in source


def test_main_tabs_are_exactly_four_clear_workspaces() -> None:
    source = _source()

    page = source.split(
        "def render_admin_leave_management_page(",
        1,
    )[1]

    expected = [
        '"Overview"',
        '"Employee Leave Accounts"',
        '"Leave Requests"',
        '"Leave Rules"',
    ]

    for label in expected:
        assert label in page

    assert "overview_tab, accounts_tab, requests_tab, rules_tab" in page
