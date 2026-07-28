"""Static tests for the wrapped Employee Master Record table."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _source() -> str:
    return (
        PROJECT_ROOT
        / "ui/pages/admin/employees_page.py"
    ).read_text(encoding="utf-8")


def test_employee_list_uses_wrapped_html_table() -> None:
    source = _source()

    assert "_render_wrapped_employee_table" in source
    assert 'class="employee-master-table"' in source
    assert "white-space: normal" in source
    assert "overflow-wrap: anywhere" in source
    assert "word-break: break-word" in source


def test_multiline_values_are_preserved() -> None:
    source = _source()

    assert '.replace("\\n", "<br>")' in source
    assert "vertical-align: top" in source


def test_dynamic_values_are_html_escaped() -> None:
    source = _source()

    assert "from html import escape" in source
    assert "escaped = escape(str(value))" in source
    assert "escape(header)" in source


def test_old_dataframe_renderer_is_removed() -> None:
    source = _source()

    assert "st.dataframe(" not in source
    assert "pd.DataFrame" not in source


def test_table_supports_small_screens() -> None:
    source = _source()

    assert "overflow-x: auto" in source
    assert "min-width: 1900px" in source
    assert "position: sticky" in source
