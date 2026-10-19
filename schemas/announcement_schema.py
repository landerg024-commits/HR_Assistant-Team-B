"""Validation values for company announcements."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator


ANNOUNCEMENT_CATEGORIES = (
    "Company Announcement",
    "Company Activity",
    "Event",
    "Reminder",
    "HR Update",
    "Policy Update",
    "Emergency Notice",
)


class AnnouncementInput(BaseModel):
    """Validated content shared by create and edit actions."""

    company_id: int
    title: str = Field(min_length=3, max_length=180)
    category: str
    summary: str = Field(min_length=5, max_length=500)
    content: str = Field(min_length=10, max_length=20000)
    is_pinned: bool = False
    publish_at: datetime | None = None
    expires_at: datetime | None = None

    @field_validator(
        "title",
        "summary",
        "content",
    )
    @classmethod
    def normalize_text(
        cls,
        value: str,
    ) -> str:
        """Trim surrounding whitespace without flattening body paragraphs."""

        return value.strip()

    @field_validator("category")
    @classmethod
    def validate_category(
        cls,
        value: str,
    ) -> str:
        cleaned = value.strip()

        if cleaned not in ANNOUNCEMENT_CATEGORIES:
            raise ValueError(
                "Select a supported announcement category."
            )

        return cleaned

    @model_validator(mode="after")
    def validate_dates(self):
        """Require expiry to occur after the planned publication."""

        if (
            self.publish_at is not None
            and self.expires_at is not None
            and self.expires_at <= self.publish_at
        ):
            raise ValueError(
                "Expiry must be after the publication date."
            )

        return self

