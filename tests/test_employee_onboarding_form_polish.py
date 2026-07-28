"""Static tests for the Employee Master Record create form."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (
        PROJECT_ROOT / relative_path
    ).read_text(encoding="utf-8")


def test_account_fields_are_inside_employee_form() -> None:
    source = _read(
        "ui/pages/admin/employees_page.py"
    )

    assert '"User Name *"' in source
    assert '"Temporary Password *"' in source
    assert '"Clearance *"' in source
    assert '"User ID"' in source
    assert '"1 - Admin"' in source
    assert '"2 - User"' in source


def test_standard_create_form_always_creates_account() -> None:
    source = _read(
        "ui/pages/admin/employees_page.py"
    )

    assert "create_login_account=True" in source
    assert '"Create Employee Record"' in source


def test_training_checklist_is_available() -> None:
    source = _read(
        "ui/pages/admin/employees_page.py"
    )

    assert "Training Checklist" in source
    assert "_parse_training_text" in source
    assert '"[x] Company Orientation' in source


def test_all_name_fields_are_present() -> None:
    source = _read(
        "ui/pages/admin/employees_page.py"
    )

    assert '"Last Name *"' in source
    assert '"First Name *"' in source
    assert '"Middle Name"' in source
    assert '"Suffix"' in source
