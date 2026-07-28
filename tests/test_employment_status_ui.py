"""UI checks for employment and account-status labels."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _source() -> str:
    return (
        PROJECT_ROOT
        / "ui/pages/admin/employees_page.py"
    ).read_text(encoding="utf-8")


def test_status_options_show_account_effect() -> None:
    source = _source()

    assert '"Employed — Account Active"' in source
    assert '"Resigned — Account Inactive"' in source
    assert '"Employment Status"' in source


def test_table_status_cell_is_multiline() -> None:
    source = _source()

    assert '"Employed\\nAccount Active"' in source
    assert '"Resigned\\nAccount Inactive"' in source


def test_edit_help_explains_reactivation() -> None:
    source = _source()

    assert "Changing back to Employed reactivates it." in source
