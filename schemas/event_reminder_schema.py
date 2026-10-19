"""Validation and smart parsing for admin event-planning reminders."""

from calendar import monthrange
from datetime import date, datetime, timedelta
import re

from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)


EVENT_REMINDER_CATEGORIES = (
    "Company Event",
    "Company Activity",
    "Holiday / Observance",
    "Training / Seminar",
    "Deadline",
    "Meeting",
    "Other",
)

EVENT_REMINDER_STATUSES = (
    "planned",
    "announcement_ready",
    "completed",
    "cancelled",
)

SMART_REMINDER_ENTRY_PATTERN = re.compile(
    r"^\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})\s*-\s*(.+?)\s*$"
)
SMART_REMINDER_HEADER_CANDIDATE_PATTERN = re.compile(
    r"^\s*\d{4}[/-]\d{1,2}[/-]\d{1,2}"
)


class ParsedReminderEntry(BaseModel):
    """Structured values extracted from one smart reminder entry box."""

    event_date: date
    title: str = Field(min_length=3, max_length=180)
    notes: str = Field(default="", max_length=5000)



def parse_smart_reminder_entry(value: str) -> ParsedReminderEntry:
    """Parse ``YYYY/MM/DD - Title`` plus optional notes from one text box."""

    normalized = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")

    first_line_index = next(
        (index for index, line in enumerate(lines) if line.strip()),
        None,
    )
    if first_line_index is None:
        raise ValueError(
            "Enter the event date and title using: YYYY/MM/DD - Event Title."
        )

    first_line = lines[first_line_index].strip()
    match = SMART_REMINDER_ENTRY_PATTERN.fullmatch(first_line)
    if match is None:
        raise ValueError(
            "The first line must use: YYYY/MM/DD - Event Title."
        )

    year, month, day, title = match.groups()
    try:
        event_date = date(int(year), int(month), int(day))
    except ValueError as error:
        raise ValueError("The event date in the Entry Box is invalid.") from error

    notes = "\n".join(lines[first_line_index + 1 :]).strip()

    return ParsedReminderEntry(
        event_date=event_date,
        title=title.strip(),
        notes=notes,
    )


def parse_smart_reminder_entries(
    value: str,
) -> tuple[ParsedReminderEntry, ...]:
    """Parse one or more reminder blocks from the shared Entry Box.

    Every line matching ``YYYY/MM/DD - Title`` starts a new reminder. This
    makes blank lines optional and still allows multi-line preparation notes.
    The complete batch is validated before the UI writes anything.
    """

    normalized = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    blocks: list[list[str]] = []
    current_block: list[str] | None = None

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if SMART_REMINDER_HEADER_CANDIDATE_PATTERN.match(stripped):
            if current_block is not None:
                blocks.append(current_block)
            current_block = [stripped]
            continue

        if current_block is None:
            if stripped:
                raise ValueError(
                    "Line "
                    f"{line_number} must start a reminder using: "
                    "YYYY/MM/DD - Event Title."
                )
            continue

        current_block.append(line)

    if current_block is not None:
        blocks.append(current_block)

    if not blocks:
        raise ValueError(
            "Enter at least one reminder using: YYYY/MM/DD - Event Title."
        )

    parsed_entries: list[ParsedReminderEntry] = []
    for entry_number, block in enumerate(blocks, start=1):
        try:
            parsed_entries.append(
                parse_smart_reminder_entry("\n".join(block))
            )
        except (ValueError, ValidationError) as error:
            raise ValueError(
                f"Reminder {entry_number}: {error}"
            ) from error

    return tuple(parsed_entries)



def subtract_calendar_month(value: datetime) -> datetime:
    """Return the same local day one calendar month earlier when possible."""

    previous_month = value.month - 1
    year = value.year
    if previous_month == 0:
        previous_month = 12
        year -= 1

    day = min(value.day, monthrange(year, previous_month)[1])
    return value.replace(year=year, month=previous_month, day=day)



def automatic_reminder_schedule(
    event_start_at: datetime,
) -> tuple[tuple[str, datetime], ...]:
    """Return the fixed one-month, two-week, and one-week milestones."""

    return (
        ("1 month before", subtract_calendar_month(event_start_at)),
        ("2 weeks before", event_start_at - timedelta(weeks=2)),
        ("1 week before", event_start_at - timedelta(weeks=1)),
    )


class EventReminderInput(BaseModel):
    """Validated values for one independent future event or activity."""

    company_id: int
    title: str = Field(min_length=3, max_length=180)
    category: str
    notes: str = Field(default="", max_length=5000)
    event_start_at: datetime
    event_end_at: datetime | None = None
    status: str = "planned"
    announcement_id: int | None = None

    @field_validator("title", "notes")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """Trim user-entered planning text."""

        return value.strip()

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        """Allow only supported reminder categories."""

        cleaned = value.strip()
        if cleaned not in EVENT_REMINDER_CATEGORIES:
            raise ValueError("Select a supported event or activity category.")
        return cleaned

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        """Allow only supported planning lifecycle values."""

        cleaned = value.strip().lower()
        if cleaned not in EVENT_REMINDER_STATUSES:
            raise ValueError("Select a supported reminder status.")
        return cleaned

    @model_validator(mode="after")
    def validate_schedule(self):
        """Require a valid optional event range."""

        if self.event_end_at is not None and self.event_end_at <= self.event_start_at:
            raise ValueError("Event end must be after the event start.")
        return self

    @property
    def reminder_schedule(self) -> tuple[tuple[str, datetime], ...]:
        """Expose the fixed automatic notification milestones."""

        return automatic_reminder_schedule(self.event_start_at)
