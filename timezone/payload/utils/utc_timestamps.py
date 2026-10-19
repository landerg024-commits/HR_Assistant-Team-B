"""Display persisted UTC instants in the application's configured timezone.

All database-created `TimestampMixin` values are instants. SQLite loses the
UTC timezone information from DateTime columns on reads; PostgreSQL can
return aware instants. This module handles both without changing saved data.

IMPORTANT: Do not use for date-only values, local appointment/shift clock
inputs, or attendance calendar dates. Those are not UTC instants.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from config.settings import get_settings


def utc_instant(value: datetime) -> datetime:
    """Interpret SQLite-naive database timestamps as UTC, not server-local."""

    if not isinstance(value, datetime):
        raise TypeError("Expected a datetime for a persisted UTC instant")
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def display_instant(value: datetime, *, timezone_name: str | None = None) -> datetime:
    """Convert a stored UTC instant to the configured display timezone."""

    zone = ZoneInfo(timezone_name or get_settings().display_timezone)
    return utc_instant(value).astimezone(zone)


def format_utc_instant(
    value: datetime | None,
    *,
    pattern: str = "%Y-%m-%d %I:%M %p",
    empty: str = "—",
    timezone_name: str | None = None,
) -> str:
    """Return a human-readable local time without mutating the UTC record."""

    if value is None:
        return empty
    return display_instant(value, timezone_name=timezone_name).strftime(pattern)


# Only instant fields receive automatic conversion in audit before/after data.
# Calendar dates (effective_date, attendance_date, hire_date) and clock-only
# values are intentionally absent. The raw audit snapshot is never modified.
_AUDIT_INSTANT_FIELDS = {
    "time_in", "time_out", "actual_time_in", "actual_time_out",
    "rounded_time_in", "rounded_time_out", "event_start_at", "event_end_at",
}


def format_audit_value(field_name: str, value: object) -> object:
    """Convert ISO UTC instants for viewing, leaving other audit values intact."""

    name = field_name.casefold().strip()
    if not (name.endswith("_at") or name in _AUDIT_INSTANT_FIELDS):
        return value
    if isinstance(value, datetime):
        candidate = value
    elif isinstance(value, str):
        # Only timestamp strings, never pure YYYY-MM-DD dates or arbitrary text.
        if "T" not in value and " " not in value:
            return value
        try:
            candidate = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    else:
        return value
    return format_utc_instant(candidate, pattern="%Y-%m-%d %I:%M:%S %p")
