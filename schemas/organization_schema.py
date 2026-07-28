"""Validation schemas for company, department, and role management.

Purpose:
- Validate administrator form values before service execution.
- Keep Streamlit pages independent from SQLAlchemy model details.
- Provide consistent length, required-field, and status validation.
"""

from pydantic import BaseModel, Field


class CompanyNameUpdate(BaseModel):
    """Values allowed when updating the current company profile."""

    company_id: int
    name: str = Field(min_length=2, max_length=200)



class CompanyThemeColorUpdate(BaseModel):
    """Company-specific primary accent color."""

    company_id: int
    primary_color: str = Field(
        min_length=7,
        max_length=7,
        pattern=r"^#[0-9A-Fa-f]{6}$",
    )


class DepartmentCreate(BaseModel):
    """Values required to create a company-scoped department."""

    company_id: int
    name: str = Field(min_length=2, max_length=150)
    code: str | None = Field(default=None, max_length=50)


class DepartmentStatusUpdate(BaseModel):
    """Values required to activate or deactivate a department."""

    company_id: int
    department_id: int
    is_active: bool


class RoleCreateRequest(BaseModel):
    """Values required to create a custom company role."""

    company_id: int
    name: str = Field(min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=255)


class RoleStatusUpdate(BaseModel):
    """Values required to activate or deactivate a custom role."""

    company_id: int
    role_id: int
    is_active: bool
