"""v8.8.65 gender-inapplicable leave row display regression tests."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_admin_and_employee_tables_display_na_for_inapplicable_rows() -> None:
    for relative_path in (
        "ui/pages/admin/leave_management_page.py",
        "ui/pages/user/leave_management_page.py",
    ):
        source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert "is_applicable" in source
        assert 'else "N/A"' in source
        assert 'if not item.is_applicable' in source or (
            'if not balance.is_applicable' in source
        )
        assert "Gender-inapplicable Maternity or" in source


def test_credit_table_row_contains_applicability_metadata() -> None:
    source = (PROJECT_ROOT / "services/leave_service.py").read_text(
        encoding="utf-8"
    )
    assert "is_applicable: bool = True" in source
    assert "is_applicable=is_applicable" in source
    assert "is_event_leave_gender_eligible" in source


def test_v8865_release_checkpoint_is_preserved() -> None:
    assert (PROJECT_ROOT / "RELEASE_v8_8_65.md").exists()
