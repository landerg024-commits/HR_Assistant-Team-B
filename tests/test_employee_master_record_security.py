"""Security and data-design tests for the Employee Master Record."""

from pathlib import Path

from sqlalchemy import inspect

import models  # noqa: F401
from database.base import Base
from sqlalchemy import create_engine


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_password_is_never_a_plain_database_column() -> None:
    """Only password_hash may exist in the users table."""

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    columns = {
        column["name"]
        for column in inspect(engine).get_columns("users")
    }

    assert "password_hash" in columns
    assert "password" not in columns


def test_full_name_is_calculated_not_stored() -> None:
    """Separate name fields remain the database source of truth."""

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    columns = {
        column["name"]
        for column in inspect(engine).get_columns("employees")
    }

    assert "first_name" in columns
    assert "middle_name" in columns
    assert "last_name" in columns
    assert "suffix" in columns
    assert "full_name" not in columns


def test_training_is_stored_as_related_rows() -> None:
    """Training must remain editable and reportable per checklist item."""

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    tables = set(inspect(engine).get_table_names())

    assert "employee_trainings" in tables


def test_edit_form_does_not_display_existing_password() -> None:
    """The UI may only offer a blank new temporary-password field."""

    source = (
        PROJECT_ROOT
        / "ui/pages/admin/employees_page.py"
    ).read_text(encoding="utf-8")

    assert '"New Temporary Password"' in source
    assert "Leave blank to keep the current password" in source
    assert '"Current Password"' not in source
