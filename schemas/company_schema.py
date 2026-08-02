"""Validation schemas for companies."""

from pydantic import BaseModel, ConfigDict, Field

from core.constants import DEFAULT_COMPANY_THEME_COLOR


class CompanyCreate(BaseModel):
    """Values required to create a company."""

    code: str = Field(min_length=2, max_length=50)
    name: str = Field(min_length=2, max_length=200)


class CompanyRead(CompanyCreate):
    """Company values returned by services."""

    id: int
    is_active: bool
    theme_primary_color: str = DEFAULT_COMPANY_THEME_COLOR
    logo_filename: str | None = None

    model_config = ConfigDict(from_attributes=True)
