"""Validated leave-management input contracts."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class LeaveTypeInput(BaseModel):
    """Create or update one leave type and its rules."""

    company_id: int
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=3, max_length=120)
    annual_credits: Decimal = Field(ge=0, le=365)
    is_paid: bool = True
    carry_over_limit: Decimal = Field(ge=0, le=365)
    # Retained for compatibility with older service callers.
    requires_attachment: bool = False
    handover_plan_requirement: Literal[
        "optional",
        "recommended",
        "required",
    ] = "optional"
    minimum_notice_days: int = Field(ge=0, le=365)
    is_active: bool = True
    apply_annual_credits_to_existing: bool = False

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return "_".join(value.strip().upper().split())

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return " ".join(value.strip().split())


class LeaveCreditAdjustmentInput(BaseModel):
    """Signed manual adjustment for one employee's annual balance."""

    company_id: int
    employee_id: int
    leave_type_id: int
    year: int = Field(ge=2000, le=2200)
    adjustment_days: Decimal = Field(ge=-365, le=365)
    reason: str = Field(min_length=3, max_length=500)
    created_by_user_id: int

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return " ".join(value.strip().split())



class LeaveCreditBalanceSetInput(BaseModel):
    """Set the exact remaining credits for one annual leave balance."""

    company_id: int
    employee_id: int
    leave_type_id: int
    year: int = Field(ge=2000, le=2200)
    new_remaining_days: Decimal = Field(ge=0, le=365)
    reason: str = Field(min_length=3, max_length=500)
    created_by_user_id: int

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return " ".join(value.strip().split())


class LeaveRequestInput(BaseModel):
    """Employee leave request delivered to the assigned manager."""

    company_id: int
    employee_id: int
    requested_by_user_id: int
    leave_type_id: int
    start_date: date
    end_date: date
    reason: str = Field(min_length=5, max_length=4000)
    handover_plan: str | None = Field(
        default=None,
        max_length=10000,
    )

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return " ".join(value.strip().split())

    @field_validator("handover_plan")
    @classmethod
    def normalize_handover_plan(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @model_validator(mode="after")
    def validate_date_order(self):
        if self.end_date < self.start_date:
            raise ValueError("End date cannot be earlier than start date.")
        if self.start_date.year != self.end_date.year:
            raise ValueError("A leave request cannot cross calendar years.")
        return self



class LeaveDecisionInput(BaseModel):
    """Approve or reject a request as its assigned manager."""

    company_id: int
    request_id: int
    manager_employee_id: int
    manager_user_id: int
    decision: Literal["approve", "reject"]
    manager_comment: str | None = Field(
        default=None,
        max_length=2000,
    )

    @field_validator("manager_comment")
    @classmethod
    def normalize_manager_comment(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.strip().split())
        return cleaned or None
