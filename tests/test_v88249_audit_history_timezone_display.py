"""Timestamp QA: UTC instants display locally; business dates remain untouched.

These are general behavior regressions, not fixed user records or QA answers.
"""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Column, DateTime, Integer, MetaData, Table, create_engine, select

from services.edit_conflict import EditConflictError
import utils.utc_timestamps as utc_timestamps
from utils.utc_timestamps import (
    display_instant,
    format_audit_value,
    format_utc_instant,
    utc_instant,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _pin_test_display_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests must not depend on a user's local .env DISPLAY_TIMEZONE."""
    monkeypatch.setattr(
        utc_timestamps, "get_settings",
        lambda: SimpleNamespace(display_timezone="Asia/Manila"),
    )


def test_sqlite_naive_utc_timestamp_displays_in_manila() -> None:
    stored = datetime(2026, 10, 16, 5, 3, 16)
    assert format_utc_instant(stored, pattern="%Y-%m-%d %I:%M:%S %p", timezone_name="Asia/Manila") == "2026-10-16 01:03:16 PM"


def test_aware_utc_has_exactly_one_conversion() -> None:
    utc = datetime(2026, 10, 16, 5, 3, 16, tzinfo=timezone.utc)
    assert display_instant(utc, timezone_name="Asia/Manila").hour == 13


def test_already_local_aware_does_not_get_double_shifted() -> None:
    local = datetime(2026, 10, 16, 13, 3, 16, tzinfo=ZoneInfo("Asia/Manila"))
    assert format_utc_instant(local, timezone_name="Asia/Manila") == "2026-10-16 01:03 PM"


def test_naive_day_rollover_is_correct() -> None:
    stored = datetime(2026, 12, 31, 23, 30)
    assert format_utc_instant(stored, timezone_name="Asia/Manila") == "2027-01-01 07:30 AM"


def test_override_timezone_respects_daylight_saving() -> None:
    stored = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
    assert format_utc_instant(stored, timezone_name="America/New_York") == "2026-07-01 08:00 AM"


def test_none_and_empty_placeholder_unchanged() -> None:
    assert format_utc_instant(None) == "—"
    assert format_utc_instant(None, empty="N/A") == "N/A"


def test_wrong_type_fails_closed() -> None:
    with pytest.raises(TypeError):
        utc_instant(date(2026, 10, 16))  # type: ignore[arg-type]


@pytest.mark.parametrize("key,raw", [
    ("hire_date", "2026-10-16"),
    ("attendance_date", "2026-10-16"),
    ("effective_date", "2026-10-16"),
    ("regular_hours_target", "8.00"),
    ("office_start_time", "08:30:00"),
    ("notes", "2026-10-16T05:03:16"),
])
def test_audit_snapshot_preserves_business_dates_and_other_fields(key: str, raw: str) -> None:
    assert format_audit_value(key, raw) == raw


@pytest.mark.parametrize("name", [
    "created_at", "updated_at", "archived_at", "completed_at", "reviewed_at",
    "time_in", "actual_time_out", "event_start_at",
])
def test_audit_snapshot_renders_utc_instants(name: str) -> None:
    assert format_audit_value(name, "2026-10-16T05:03:16") == "2026-10-16 01:03:16 PM"


def test_audit_snapshot_aware_utc_iso() -> None:
    assert format_audit_value("updated_at", "2026-10-16T05:03:16+00:00") == "2026-10-16 01:03:16 PM"


def test_audit_snapshot_unparseable_value_stays_intact() -> None:
    assert format_audit_value("updated_at", "unknown") == "unknown"
    assert format_audit_value("updated_at", "2026-10-16") == "2026-10-16"


def test_mixed_timezone_sort_is_safe_for_central_audit() -> None:
    values = [
        datetime(2026, 10, 16, 5, 3, tzinfo=timezone.utc),
        datetime(2026, 10, 16, 6, 0),
        datetime(2026, 10, 16, 13, 30, tzinfo=ZoneInfo("Asia/Manila")),
    ]
    assert [item.hour for item in sorted(values, key=utc_instant)] == [5, 13, 6]


def test_sqlite_roundtrip_strips_timezone_and_formatter_restores_local() -> None:
    # The app uses DateTime(timezone=True). SQLite doesn't retain tzinfo.
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata = MetaData()
    audit_events = Table(
        "audit_events_demo", metadata,
        Column("id", Integer, primary_key=True),
        Column("created_at", DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            audit_events.insert().values(
                created_at=datetime(2026, 10, 16, 5, 3, 16, tzinfo=timezone.utc)
            )
        )
        stored = connection.execute(select(audit_events.c.created_at)).scalar_one()
    assert stored.tzinfo is None
    assert format_utc_instant(stored, timezone_name="Asia/Manila") == "2026-10-16 01:03 PM"
    engine.dispose()


def test_conflict_message_uses_local_time_not_raw_utc() -> None:
    err = EditConflictError(
        module="Employees", entity_label="Test", latest_version=2,
        latest_values={}, updated_by="Admin", updated_at=datetime(2026, 10, 16, 5, 3),
    )
    assert "October 16, 2026 at 01:03 PM" in str(err)


def test_display_fix_does_not_change_database_default_or_data_migration() -> None:
    # Existing audit time is immutable; UI reads it rather than rewriting rows.
    db_model = (ROOT / "database/base.py").read_text(encoding="utf-8")
    assert "server_default=func.now()" in db_model
    page = (ROOT / "ui/pages/admin/audit_trail_page.py").read_text(encoding="utf-8")
    assert '"Date / Time": _display_datetime(entry.occurred_at)' in page
    assert "format_utc_instant(value" in page


def test_all_known_unconverted_history_displays_use_shared_formatter() -> None:
    expected = {
        "ui/pages/admin/employees_page.py": ["history.created_at", "employee.archived_at"],
        "ui/pages/admin/onboarding_management.py": ["item.completed_at"],
        "ui/pages/admin/hr_contacts_management.py": ["contact.archived_at"],
        "ui/components/disciplinary_records.py": ["record.archived_at"],
        "ui/pages/user/leave_management_page.py": ["balance.updated_at"],
    }
    for path, expressions in expected.items():
        content = (ROOT / path).read_text(encoding="utf-8")
        for expr in expressions:
            assert f"format_utc_instant({expr}" in content
