"""Regression checks for v8.8.36 gender options and live age display."""

from pathlib import Path


PAGE = Path("ui/pages/admin/employees_page.py")


def _source() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_gender_is_limited_to_male_and_female() -> None:
    source = _source()
    assert 'GENDER_OPTIONS = ["Male", "Female"]' in source
    assert "Non-binary" not in source
    assert "Prefer not to say" not in source


def test_create_age_widget_key_changes_with_birth_date() -> None:
    source = _source()
    assert 'key=f"create_age_display_{date_of_birth or \'none\'}"' in source


def test_edit_age_widget_key_changes_with_birth_date() -> None:
    source = _source()
    assert 'key=prefix + f"age_display_{date_of_birth or \'none\'}"' in source
