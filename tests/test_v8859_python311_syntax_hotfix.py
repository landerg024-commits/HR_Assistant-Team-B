"""Regression checks for the Python 3.11 employee leave page syntax hotfix."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EMPLOYEE_LEAVE_PAGE = (
    PROJECT_ROOT / "ui" / "pages" / "user" / "leave_management_page.py"
)


def test_leave_type_formatter_avoids_multiline_f_string_expression() -> None:
    """Keep the selectbox label compatible with the project's Python 3.11 runtime."""

    source = EMPLOYEE_LEAVE_PAGE.read_text(encoding="utf-8")

    assert "def _format_leave_type_option(value: int) -> str:" in source
    assert 'format_func=_format_leave_type_option' in source
    assert 'f"{_days(\n' not in source
