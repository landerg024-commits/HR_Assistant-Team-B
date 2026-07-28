"""Validation schemas for companies."""

from pydantic import BaseModel, ConfigDict, Field


class CompanyCreate(BaseModel):
    """Values required to create a company."""

    code: str = Field(min_length=2, max_length=50)
    name: str = Field(min_length=2, max_length=200)


class CompanyRead(CompanyCreate):
    """Company values returned by services."""

    id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
