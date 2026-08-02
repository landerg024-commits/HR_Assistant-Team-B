"""Employee form layout and searchable-list regression tests."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _source() -> str:
    return (
        PROJECT_ROOT
        / "ui/pages/admin/employees_page.py"
    ).read_text(encoding="utf-8")


def test_add_and_edit_forms_use_bordered_information_cards() -> None:
    source = _source()

    assert 'key="employee_create_information_card"' in source
    assert 'key="employee_create_account_card"' in source
    assert 'employee_edit_information_card_' in source
    assert 'employee_edit_account_card_' in source
    assert source.count("border=True") >= 4


def test_employee_information_uses_reference_grid_order() -> None:
    source = _source()

    assert "last_column, first_column, middle_column, suffix_column" in source
    assert "department_column, manager_column, position_column" in source
    assert "status_column, hire_column" in source
    assert 'st.markdown("### Training Checklist")' in source
    assert 'st.markdown("### Account Information")' in source


def test_employee_list_has_search_and_result_count() -> None:
    source = _source()

    assert "def _filter_employees(" in source
    assert '"Search Employees"' in source
    assert 'key="employee_master_search"' in source
    assert "Showing {len(filtered)} of {len(employees)}" in source


def test_employee_list_shows_five_rows_in_scroll_viewport() -> None:
    source = _source()

    assert "height: auto" in source
    assert "max-height: 432px" in source
    assert "overflow-x: scroll" in source
    assert "overflow-y: scroll" in source
    assert "scrollbar-gutter: stable both-edges" in source
    assert ".employee-table-shell::-webkit-scrollbar" in source
    assert "height: 72px" in source
    assert "max-height: 56px" in source


def test_table_still_escapes_dynamic_employee_values() -> None:
    source = _source()

    assert "escape(header)" in source
    assert "escaped = escape(str(value))" in source
    assert "_html_cell(row.get(header, ''))" in source
