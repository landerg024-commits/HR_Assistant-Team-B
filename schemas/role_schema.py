"""Validation schemas for application roles."""

from pydantic import BaseModel, ConfigDict, Field


class RoleCreate(BaseModel):
    """Values required to create a company-scoped role."""

    company_id: int
    name: str = Field(min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=255)
    is_system_role: bool = False


class RoleRead(RoleCreate):
    """Role values returned by services."""

    id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
