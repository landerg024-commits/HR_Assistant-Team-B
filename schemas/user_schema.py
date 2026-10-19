"""Validation schemas for users and employees."""

from datetime import date

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    """Values required before password hashing is applied."""

    company_id: int
    role_id: int
    clearance: int = Field(default=2, ge=1, le=2)
    username: str = Field(min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserRead(BaseModel):
    """Safe user representation without a password hash."""

    id: int
    company_id: int
    role_id: int
    clearance: int
    username: str
    email: EmailStr
    is_active: bool
    must_change_password: bool

    model_config = ConfigDict(from_attributes=True)


class EmployeeCreate(BaseModel):
    """Values required to create an employee profile."""

    company_id: int
    employee_number: str = Field(min_length=1, max_length=80)
    first_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    suffix: str | None = Field(default=None, max_length=30)
    work_email: EmailStr | None = None
    telephone_mobile_no: str | None = Field(
        default=None,
        max_length=50,
    )
    job_title: str | None = Field(default=None, max_length=150)
    hire_date: date | None = None
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, max_length=50)
    civil_status: str | None = Field(default=None, max_length=50)
    employment_status: str = "employed"
    department_id: int | None = None
    manager_id: int | None = None
    leader_id: int | None = None
    user_id: int | None = None


class EmployeeRead(EmployeeCreate):
    """Employee representation returned by services."""

    id: int
    employment_status: str
    full_name: str

    model_config = ConfigDict(from_attributes=True)
