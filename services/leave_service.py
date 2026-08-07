"""Leave credits, requests, manager email delivery, and HR monitoring."""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config.settings import Settings, get_settings
from integrations.email.email_sender import (
    EmailAttachment,
    EmailDeliveryError,
    EmailSender,
    OutboundEmail,
    build_email_sender,
)
from models.employee import Employee
from models.leave_balance import LeaveBalance
from models.leave_credit_transaction import LeaveCreditTransaction
from models.leave_request import LeaveRequest
from models.leave_type import LeaveType
from models.user import User
from modules.leave.leave_file_storage import LeaveFileStorage
from repositories.employee_repository import EmployeeRepository
from repositories.leave_repository import (
    LeaveBalanceRepository,
    LeaveCreditTransactionRepository,
    LeaveRequestRepository,
    LeaveTypeRepository,
)
from repositories.user_repository import UserRepository
from schemas.leave_schema import (
    LeaveCreditAdjustmentInput,
    LeaveCreditBalanceSetInput,
    LeaveDecisionInput,
    LeaveRequestInput,
    LeaveTypeInput,
)
from services.notification_service import NotificationService


DEFAULT_LEAVE_TYPES = (
    {
        # Vacation Leave receives a 15-day January accrual. Employees who
        # have completed five service years by January 1 receive 17 days.
        "code": "VACATION",
        "name": "Vacation Leave",
        "annual_credits": Decimal("15.00"),
        "is_paid": True,
        "carry_over_limit": Decimal("0.00"),
        "requires_attachment": False,
        "minimum_notice_days": 5,
        "handover_plan_requirement": "recommended",
    },
    {
        "code": "SICK",
        "name": "Sick Leave",
        "annual_credits": Decimal("15.00"),
        "is_paid": True,
        "carry_over_limit": Decimal("0.00"),
        "requires_attachment": False,
        "minimum_notice_days": 0,
        "handover_plan_requirement": "optional",
    },
    {
        # Emergency Leave is included in the Vacation Leave entitlement.
        # Phase 2 therefore gives it no separate annual credit. Its protected
        # three-day usage allowance is enforced in the later EL phase.
        "code": "EMERGENCY",
        "name": "Emergency Leave",
        "annual_credits": Decimal("0.00"),
        "is_paid": True,
        "carry_over_limit": Decimal("0.00"),
        "requires_attachment": False,
        "minimum_notice_days": 0,
        "handover_plan_requirement": "optional",
    },
    {
        # Phase 5 grants five days once, after manager approval of the
        # employee's single qualifying Honeymoon Leave request.
        "code": "HONEYMOON",
        "name": "Honeymoon Leave",
        "annual_credits": Decimal("0.00"),
        "is_paid": True,
        "carry_over_limit": Decimal("0.00"),
        "requires_attachment": False,
        "minimum_notice_days": 0,
        "handover_plan_requirement": "recommended",
    },
    {
        # Phase 5 grants 105 days for each manager-approved qualifying event.
        "code": "MATERNITY",
        "name": "Maternity Leave",
        "annual_credits": Decimal("0.00"),
        "is_paid": True,
        "carry_over_limit": Decimal("0.00"),
        "requires_attachment": False,
        "minimum_notice_days": 0,
        "handover_plan_requirement": "recommended",
    },
    {
        # Phase 5 grants seven days for each manager-approved qualifying event.
        "code": "PATERNITY",
        "name": "Paternity Leave",
        "annual_credits": Decimal("0.00"),
        "is_paid": True,
        "carry_over_limit": Decimal("0.00"),
        "requires_attachment": False,
        "minimum_notice_days": 0,
        "handover_plan_requirement": "recommended",
    },
    {
        # Phase 5 grants seven days for each manager-approved qualifying event.
        "code": "BEREAVEMENT",
        "name": "Bereavement Leave",
        "annual_credits": Decimal("0.00"),
        "is_paid": True,
        "carry_over_limit": Decimal("0.00"),
        "requires_attachment": False,
        "minimum_notice_days": 0,
        "handover_plan_requirement": "recommended",
    },
    {
        # LWOP remains an internal fallback and is intentionally excluded
        # from the seven-row employee leave-credit table.
        "code": "LWOP",
        "name": "Leave Without Pay",
        "annual_credits": Decimal("0.00"),
        "is_paid": False,
        "carry_over_limit": Decimal("0.00"),
        "requires_attachment": False,
        "minimum_notice_days": 0,
        "handover_plan_requirement": "recommended",
    },
)

LEAVE_CREDIT_TABLE_CODES = (
    "VACATION",
    "EMERGENCY",
    "SICK",
    "HONEYMOON",
    "MATERNITY",
    "PATERNITY",
    "BEREAVEMENT",
)
LEAVE_CREDIT_TABLE_ORDER = {
    code: index
    for index, code in enumerate(LEAVE_CREDIT_TABLE_CODES)
}

SERVICE_BONUS_AFTER_YEARS = 5
SERVICE_BONUS_DAYS = Decimal("2.00")
SERVICE_BONUS_CODES = {"VACATION", "SICK"}
ANNUAL_ACCRUAL_CODES = {"VACATION", "SICK"}
ANNUAL_BASE_CREDIT = Decimal("15.00")

# Emergency Leave is a protected annual usage allowance inside Vacation
# Leave. It never creates additional credits; approved EL days consume VL.
EMERGENCY_USAGE_LIMIT = Decimal("3.00")
EMERGENCY_ACTIVE_STATUSES = {
    "scheduled",
    "approved",
    "in_progress",
    "completed",
}

# Event-based leave is granted only when a manager approves the related
# request. Each approved request represents one qualifying event. Honeymoon
# Leave is the only lifetime one-time benefit; the other event leave types may
# receive another fixed grant for a later approved qualifying event.
EVENT_LEAVE_ENTITLEMENTS = {
    "HONEYMOON": Decimal("5.00"),
    "MATERNITY": Decimal("105.00"),
    "PATERNITY": Decimal("7.00"),
    "BEREAVEMENT": Decimal("7.00"),
}
EVENT_LEAVE_CODES = set(EVENT_LEAVE_ENTITLEMENTS)
EVENT_LEAVE_GRANT_TRANSACTION = "event_leave_entitlement_grant"

# Maternity and Paternity eligibility follows the employee gender recorded
# in the employee master file. The service layer remains the source of truth
# so direct calls and old pending requests cannot bypass the UI filter.
EVENT_LEAVE_GENDER_REQUIREMENTS = {
    "MATERNITY": "FEMALE",
    "PATERNITY": "MALE",
}

EVENT_LEAVE_NON_REJECTED_STATUSES = {
    "pending_manager_approval",
    "scheduled",
    "approved",
    "in_progress",
    "completed",
}

# Fixed balances that may remain usable after the January annual credit.
# Any opening ledger amount above these limits is transferred to the
# Converted to Cash column and is no longer part of available credits.
CASH_CONVERSION_LIMITS = {
    "SICK": Decimal("15.00"),
    "VACATION": Decimal("45.00"),
}
CASH_CONVERSION_TRANSACTION = "january_cash_conversion"
CASH_CONVERSION_LIMIT_ENFORCEMENT_TRANSACTION = (
    "cash_conversion_limit_enforcement"
)

# Only exact legacy defaults are upgraded automatically. Company-specific
# values that HR already customized remain untouched.
LEGACY_DEFAULT_UPGRADES = {
    "VACATION": {
        "annual_credits": ({Decimal("42.00")}, Decimal("15.00")),
        "carry_over_limit": ({Decimal("5.00")}, Decimal("0.00")),
    },
    "SICK": {
        "annual_credits": ({Decimal("10.00")}, Decimal("15.00")),
    },
    "EMERGENCY": {
        "annual_credits": ({Decimal("3.00")}, Decimal("0.00")),
    },
}



@dataclass(frozen=True, slots=True)
class LeaveCreditBalanceSetResult:
    """Outcome after setting and enforcing one leave-credit value."""

    balance: LeaveBalance
    previous_remaining: Decimal
    requested_remaining: Decimal
    new_remaining: Decimal
    converted_to_cash: Decimal


@dataclass(frozen=True, slots=True)
class LeaveSubmissionResult:
    """Outcome returned after recording and emailing a request."""

    request: LeaveRequest
    email_sent: bool
    message: str


@dataclass(frozen=True, slots=True)
class LeaveAllocationPlan:
    """Paid-credit and automatic LWOP split for one leave request."""

    primary_balance: LeaveBalance | None
    primary_days: Decimal
    fallback_balance: LeaveBalance | None
    fallback_days: Decimal
    lwop_days: Decimal

    @property
    def paid_days(self) -> Decimal:
        return self.primary_days + self.fallback_days


@dataclass(frozen=True, slots=True)
class EmergencyAllowanceSummary:
    """Annual EL usage tracked separately while credits remain in VL."""

    used_days: Decimal
    reserved_days: Decimal
    remaining_days: Decimal
    last_updated: datetime | None = None


@dataclass(frozen=True, slots=True)
class LeaveCreditTableRow:
    """Employee-facing leave ledger row with eligibility display metadata."""

    leave_type: LeaveType
    beginning_credit_days: Decimal
    credit_days: Decimal
    adjustment_days: Decimal
    used_days: Decimal
    reserved_days: Decimal
    available_credits: Decimal
    converted_to_cash_days: Decimal
    updated_at: datetime | None
    is_applicable: bool = True


class LeaveService:
    """Coordinate all leave-management business rules."""

    def __init__(self, session: Session, *, settings: Settings | None = None, email_sender: EmailSender | None = None, storage: LeaveFileStorage | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.email_sender = email_sender or build_email_sender(self.settings)
        self.storage = storage or LeaveFileStorage(self.settings.leave_attachment_dir)
        self.leave_type_repository = LeaveTypeRepository(session)
        self.balance_repository = LeaveBalanceRepository(session)
        self.request_repository = LeaveRequestRepository(session)
        self.transaction_repository = LeaveCreditTransactionRepository(session)
        self.employee_repository = EmployeeRepository(session)
        self.user_repository = UserRepository(session)
        self.notification_service = NotificationService(session)

    def _today(self) -> date:
        return datetime.now(ZoneInfo(self.settings.display_timezone)).date()

    @staticmethod
    def _business_days(start_date: date, end_date: date) -> Decimal:
        days = Decimal("0.00")
        current = start_date
        from datetime import timedelta
        while current <= end_date:
            if current.weekday() < 5:
                days += Decimal("1.00")
            current += timedelta(days=1)
        return days

    @classmethod
    def calculate_working_days(
        cls,
        start_date: date,
        end_date: date,
    ) -> Decimal:
        """Return Monday-to-Friday days for live form preview."""

        if end_date < start_date:
            return Decimal("0.00")

        return cls._business_days(start_date, end_date)

    @staticmethod
    def _email_for_employee(employee: Employee | None) -> str | None:
        if employee is None:
            return None
        if employee.work_email and employee.work_email.strip():
            return employee.work_email.strip()
        if employee.user and employee.user.email:
            return employee.user.email.strip()
        return None

    @staticmethod
    def completed_service_years(
        hire_date: date | None,
        as_of: date,
    ) -> int:
        """Return completed service years without counting partial years."""

        if hire_date is None or as_of < hire_date:
            return 0

        years = as_of.year - hire_date.year
        if (as_of.month, as_of.day) < (
            hire_date.month,
            hire_date.day,
        ):
            years -= 1
        return max(0, years)

    @staticmethod
    def _round_to_half_day(value: Decimal) -> Decimal:
        """Round a prorated entitlement to the nearest half day."""

        return (
            (value * Decimal("2"))
            .quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            / Decimal("2")
        ).quantize(Decimal("0.00"))

    @staticmethod
    def _annual_processing_date(year: int) -> date:
        """Return the effective date of the yearly SL/VL accrual."""

        return date(year, 1, 1)

    def _allocation_reference_date(
        self,
        *,
        year: int,
        as_of: date | None = None,
    ) -> date:
        """Return the January processing date for annual entitlement rules.

        ``as_of`` is retained for compatibility with callers and tests, but a
        mid-year service anniversary must not change an already processed
        annual credit. The +2 tenure increase is evaluated only on January 1.
        """

        return self._annual_processing_date(year)

    def calculate_annual_allocation(
        self,
        *,
        employee: Employee,
        leave_type: LeaveType,
        year: int,
        as_of: date | None = None,
    ) -> Decimal:
        """Compute one employee's January SL/VL credit for a calendar year.

        Rules:
        - Vacation Leave and Sick Leave receive 15 days each every January.
        - Employees with at least five completed service years on January 1
          receive 17 days for each of those two leave types.
        - A service anniversary reached after January 1 applies next year.
        - The hire year keeps the accepted prorated entitlement behavior.
        - Other leave types do not receive an annual Phase 2 accrual.
        """

        code = (leave_type.code or "").strip().upper()
        hire_date = employee.hire_date
        processing_date = self._annual_processing_date(year)

        if code not in ANNUAL_ACCRUAL_CODES:
            return Decimal("0.00")

        if hire_date is not None:
            if year < hire_date.year:
                return Decimal("0.00")
            if as_of is not None and year == hire_date.year and as_of < hire_date:
                return Decimal("0.00")

        # The standard policy is fixed at 15 days. The Leave Type setting is
        # still synchronized to 15 for existing databases by the safe default
        # upgrade, while the computation remains explicit and auditable here.
        allocation = ANNUAL_BASE_CREDIT
        service_years = self.completed_service_years(
            hire_date,
            processing_date,
        )
        if service_years >= SERVICE_BONUS_AFTER_YEARS:
            allocation += SERVICE_BONUS_DAYS

        if hire_date is not None and year == hire_date.year:
            remaining_months = 13 - hire_date.month
            allocation = self._round_to_half_day(
                allocation
                * Decimal(remaining_months)
                / Decimal("12")
            )

        return max(Decimal("0.00"), allocation)

    def entitlement_summary(
        self,
        *,
        employee: Employee,
        year: int,
        as_of: date | None = None,
    ) -> dict[str, Decimal | int | str]:
        """Return the standard combined leave entitlement for UI display."""

        leave_types = {
            item.code.upper(): item
            for item in self.list_leave_types(employee.company_id)
        }
        reference_date = self._annual_processing_date(year)

        def allocation(code: str) -> Decimal:
            leave_type = leave_types.get(code)
            if leave_type is None:
                return Decimal("0.00")
            return self.calculate_annual_allocation(
                employee=employee,
                leave_type=leave_type,
                year=year,
                as_of=as_of,
            )

        regular_vacation = allocation("VACATION")
        emergency = Decimal("0.00")
        sick = allocation("SICK")
        return {
            "service_years": self.completed_service_years(
                employee.hire_date,
                reference_date,
            ),
            "regular_vacation": regular_vacation,
            "emergency": emergency,
            "vacation_total": regular_vacation,
            "sick": sick,
            "lwop": Decimal("0.00"),
            "basis": (
                "Hire-year prorated"
                if employee.hire_date is not None
                and year == employee.hire_date.year
                else "January annual accrual"
            ),
        }

    def ensure_default_leave_types(self, company_id: int) -> list[LeaveType]:
        """Create defaults and safely upgrade untouched legacy allocations."""

        changed = False
        for spec in DEFAULT_LEAVE_TYPES:
            existing = self.leave_type_repository.get_by_code(
                company_id,
                spec["code"],
            )
            if existing is None:
                self.session.add(
                    LeaveType(
                        company_id=company_id,
                        is_active=True,
                        **spec,
                    )
                )
                changed = True
                continue

            upgrades = LEGACY_DEFAULT_UPGRADES.get(
                spec["code"],
                {},
            )
            for field_name, (legacy_values, new_value) in upgrades.items():
                current_value = Decimal(getattr(existing, field_name))
                if current_value in legacy_values:
                    setattr(existing, field_name, new_value)
                    changed = True

        if changed:
            self.session.commit()
        return self.leave_type_repository.list_company(company_id)

    @staticmethod
    def _sync_credit_table_columns(balance: LeaveBalance) -> bool:
        """Mirror the legacy ledger into the Phase 1 table columns.

        Returns True only when at least one persisted value changes. This
        keeps old records accurate without replacing or deleting them.
        """

        expected_beginning = Decimal(balance.carry_over_days)
        # Credit contains only automatic annual accruals or approved
        # event grants. Administrator corrections remain independently
        # visible in Adjustment and must never overwrite the credit source.
        expected_credit = Decimal(balance.allocated_days)
        changed = False

        if Decimal(balance.beginning_credit_days) != expected_beginning:
            balance.beginning_credit_days = expected_beginning
            changed = True

        if Decimal(balance.credit_days) != expected_credit:
            balance.credit_days = expected_credit
            changed = True

        return changed


    def _normalize_event_credit_classification(
        self,
        *,
        balance: LeaveBalance,
        leave_type: LeaveType,
    ) -> bool:
        """Move legacy event grants from Adjustment into Credit.

        Phase 5 originally stored approved event grants in the legacy
        adjustment bucket so they could coexist with annual accrual logic.
        The explicit Adjustment column now requires those immutable grant
        transactions to appear as Credit instead. Only the amount supported
        by event-grant audit transactions is reclassified, so unrelated
        repair adjustments remain untouched.
        """

        code = (leave_type.code or "").strip().upper()
        if code not in EVENT_LEAVE_CODES:
            return False

        grant_total = self.session.scalar(
            select(
                func.coalesce(
                    func.sum(LeaveCreditTransaction.amount_days),
                    Decimal("0.00"),
                )
            ).where(
                LeaveCreditTransaction.leave_balance_id == balance.id,
                LeaveCreditTransaction.transaction_type
                == EVENT_LEAVE_GRANT_TRANSACTION,
            )
        )
        grant_total = max(Decimal("0.00"), Decimal(grant_total or 0))
        allocated = Decimal(balance.allocated_days)
        adjustment = Decimal(balance.adjustment_days)
        amount_to_move = min(
            max(Decimal("0.00"), grant_total - allocated),
            max(Decimal("0.00"), adjustment),
        )
        if amount_to_move <= Decimal("0.00"):
            return False

        balance.allocated_days = allocated + amount_to_move
        balance.adjustment_days = adjustment - amount_to_move
        return True


    def _normalize_emergency_balance(
        self,
        *,
        balance: LeaveBalance,
        leave_type: LeaveType,
    ) -> bool:
        """Remove legacy standalone EL credits without deleting requests.

        Phase 4 treats leave requests as the source of EL usage and Vacation
        Leave as the only paid-credit source. Older standalone EL ledger
        values are therefore cleared once with an audit entry.
        """

        code = (leave_type.code or "").strip().upper()
        if code != "EMERGENCY":
            return False

        tracked_values = (
            Decimal(balance.allocated_days),
            Decimal(balance.carry_over_days),
            Decimal(balance.adjustment_days),
            Decimal(balance.used_days),
            Decimal(balance.reserved_days),
            Decimal(balance.beginning_credit_days),
            Decimal(balance.credit_days),
            Decimal(balance.converted_to_cash_days),
        )
        if all(value == Decimal("0.00") for value in tracked_values):
            return False

        prior_usable = Decimal(balance.available_credits)
        balance.allocated_days = Decimal("0.00")
        balance.carry_over_days = Decimal("0.00")
        balance.adjustment_days = Decimal("0.00")
        balance.used_days = Decimal("0.00")
        balance.reserved_days = Decimal("0.00")
        balance.beginning_credit_days = Decimal("0.00")
        balance.credit_days = Decimal("0.00")
        balance.converted_to_cash_days = Decimal("0.00")

        self.session.add(
            LeaveCreditTransaction(
                company_id=balance.company_id,
                employee_id=balance.employee_id,
                leave_type_id=balance.leave_type_id,
                leave_balance_id=balance.id,
                transaction_type="emergency_credit_normalization",
                amount_days=-prior_usable,
                note=(
                    "Phase 4 normalization: Emergency Leave is a maximum "
                    "three-day annual usage allowance inside Vacation Leave, "
                    "not a separate credit balance. Existing leave requests "
                    "and their history were preserved."
                ),
            )
        )
        return True

    def _repair_negative_balance(
        self,
        balance: LeaveBalance,
    ) -> Decimal:
        """Bring one invalid legacy balance back to zero with an audit entry.

        Older test data may contain more used/reserved days than the recorded
        credits. The history is preserved; only the internal adjustment is
        increased by the exact deficit so the usable balance becomes zero.
        Re-running this method is idempotent.
        """

        raw_available = Decimal(
            balance.calculated_available_credits
        ).quantize(Decimal("0.01"))

        if raw_available >= Decimal("0.00"):
            return Decimal("0.00")

        repair_days = -raw_available
        balance.adjustment_days = (
            Decimal(balance.adjustment_days) + repair_days
        )
        self._sync_credit_table_columns(balance)

        self.session.add(
            LeaveCreditTransaction(
                company_id=balance.company_id,
                employee_id=balance.employee_id,
                leave_type_id=balance.leave_type_id,
                leave_balance_id=balance.id,
                transaction_type="negative_balance_repair",
                amount_days=repair_days,
                note=(
                    "Automatic non-negative balance safeguard: "
                    f"legacy balance {raw_available} day(s) was corrected "
                    "to 0.00 without deleting leave usage or request history."
                ),
            )
        )
        return repair_days

    @staticmethod
    def _validate_nonnegative_balance(balance: LeaveBalance) -> None:
        """Block any write that would persist a negative usable balance."""

        raw_available = Decimal(
            balance.calculated_available_credits
        ).quantize(Decimal("0.01"))
        if raw_available < Decimal("0.00"):
            raise ValueError(
                "Insufficient leave credits. The balance cannot go below "
                "zero; use Leave Without Pay for the uncovered days."
            )

    @staticmethod
    def credit_table_balances(balances) -> list[LeaveBalance]:
        """Return the seven employee-facing leave rows in required order."""

        return sorted(
            (
                balance
                for balance in balances
                if balance.leave_type.code.upper()
                in LEAVE_CREDIT_TABLE_ORDER
            ),
            key=lambda balance: LEAVE_CREDIT_TABLE_ORDER[
                balance.leave_type.code.upper()
            ],
        )

    @staticmethod
    def _emergency_paid_days(request: LeaveRequest) -> Decimal:
        """Return the approved paid EL portion, excluding automatic LWOP."""

        paid = (
            Decimal(request.primary_credit_days or Decimal("0.00"))
            + Decimal(request.fallback_credit_days or Decimal("0.00"))
        )
        return max(Decimal("0.00"), paid)

    @staticmethod
    def event_leave_entitlement(
        leave_type_or_code: LeaveType | str,
    ) -> Decimal:
        """Return the fixed grant for one qualifying event leave request."""

        code = (
            leave_type_or_code.code
            if isinstance(leave_type_or_code, LeaveType)
            else leave_type_or_code
        )
        return EVENT_LEAVE_ENTITLEMENTS.get(
            (code or "").strip().upper(),
            Decimal("0.00"),
        )

    @staticmethod
    def normalized_employee_gender(employee: Employee | None) -> str:
        """Return a stable MALE/FEMALE value for eligibility checks."""

        raw_value = (employee.gender if employee is not None else None)
        normalized = (raw_value or "").strip().upper()
        aliases = {
            "M": "MALE",
            "MALE": "MALE",
            "F": "FEMALE",
            "FEMALE": "FEMALE",
        }
        return aliases.get(normalized, normalized)

    @classmethod
    def event_leave_gender_eligibility(
        cls,
        *,
        employee: Employee | None,
        leave_type_or_code: LeaveType | str,
    ) -> tuple[bool, str | None]:
        """Return whether an employee may use the selected event leave."""

        code = (
            leave_type_or_code.code
            if isinstance(leave_type_or_code, LeaveType)
            else leave_type_or_code
        )
        normalized_code = (code or "").strip().upper()
        required_gender = EVENT_LEAVE_GENDER_REQUIREMENTS.get(
            normalized_code
        )
        if required_gender is None:
            return True, None

        employee_gender = cls.normalized_employee_gender(employee)
        if employee_gender == required_gender:
            return True, None

        leave_name = (
            leave_type_or_code.name
            if isinstance(leave_type_or_code, LeaveType)
            else normalized_code.title()
        )
        required_label = required_gender.title()
        if employee_gender not in {"MALE", "FEMALE"}:
            return (
                False,
                f"{leave_name} requires the employee gender to be recorded "
                f"as {required_label}. Update the employee profile before "
                "filing or approving this request.",
            )

        return (
            False,
            f"{leave_name} is available only to employees recorded as "
            f"{required_label}.",
        )

    @classmethod
    def is_event_leave_gender_eligible(
        cls,
        *,
        employee: Employee | None,
        leave_type_or_code: LeaveType | str,
    ) -> bool:
        """Convenience boolean used by the employee request UI."""

        eligible, _ = cls.event_leave_gender_eligibility(
            employee=employee,
            leave_type_or_code=leave_type_or_code,
        )
        return eligible

    @classmethod
    def _validate_event_leave_gender_eligibility(
        cls,
        *,
        employee: Employee | None,
        leave_type_or_code: LeaveType | str,
    ) -> None:
        """Reject ineligible Maternity/Paternity requests consistently."""

        eligible, message = cls.event_leave_gender_eligibility(
            employee=employee,
            leave_type_or_code=leave_type_or_code,
        )
        if not eligible:
            raise ValueError(message or "The selected leave is unavailable.")

    @staticmethod
    def leave_entitlement_display(leave_type_or_code: LeaveType | str) -> str:
        """Return the policy allowance label for explanatory UI text."""

        code = (
            leave_type_or_code.code
            if isinstance(leave_type_or_code, LeaveType)
            else leave_type_or_code
        )
        normalized_code = (code or "").strip().upper()
        labels = {
            "VACATION": "15 / 17 annually",
            "EMERGENCY": "3 max/year from VL",
            "SICK": "15 / 17 annually",
            "HONEYMOON": "5 one-time",
            "MATERNITY": "105 per event · Female",
            "PATERNITY": "7 per event · Male",
            "BEREAVEMENT": "7 per event",
        }
        return labels.get(normalized_code, "—")

    @staticmethod
    def supports_cash_conversion(
        leave_type_or_code: LeaveType | str,
    ) -> bool:
        """Return True only for leave types allowed to convert to cash."""

        code = (
            leave_type_or_code.code
            if isinstance(leave_type_or_code, LeaveType)
            else leave_type_or_code
        )
        return (code or "").strip().upper() in CASH_CONVERSION_LIMITS

    def _honeymoon_request_exists(
        self,
        *,
        company_id: int,
        employee_id: int,
        exclude_request_id: int | None = None,
    ) -> bool:
        """Return whether the employee already claimed or filed Honeymoon Leave."""

        for request in self.request_repository.list_employee(
            company_id,
            employee_id,
        ):
            code = (
                request.leave_type.code
                if request.leave_type is not None
                else ""
            ).strip().upper()
            if code != "HONEYMOON":
                continue
            if (
                exclude_request_id is not None
                and request.id == exclude_request_id
            ):
                continue
            if request.status in EVENT_LEAVE_NON_REJECTED_STATUSES:
                return True
        return False

    def event_leave_preview_entitlement(
        self,
        *,
        company_id: int,
        employee_id: int,
        leave_type: LeaveType,
    ) -> Decimal:
        """Return the grant expected if a new event request is approved."""

        code = (leave_type.code or "").strip().upper()
        entitlement = self.event_leave_entitlement(code)
        if entitlement <= Decimal("0.00"):
            return Decimal("0.00")

        employee = self.employee_repository.get_with_details(
            company_id=company_id,
            employee_id=employee_id,
        )
        if not self.is_event_leave_gender_eligible(
            employee=employee,
            leave_type_or_code=leave_type,
        ):
            return Decimal("0.00")
        if code == "HONEYMOON" and self._honeymoon_request_exists(
            company_id=company_id,
            employee_id=employee_id,
        ):
            return Decimal("0.00")
        return entitlement

    def _event_grant_already_posted(
        self,
        request: LeaveRequest,
    ) -> bool:
        """Keep one immutable entitlement grant per approved event request."""

        count = self.session.scalar(
            select(func.count(LeaveCreditTransaction.id)).where(
                LeaveCreditTransaction.leave_request_id == request.id,
                LeaveCreditTransaction.transaction_type
                == EVENT_LEAVE_GRANT_TRANSACTION,
            )
        )
        return bool(count)

    def _grant_event_leave_entitlement(
        self,
        *,
        request: LeaveRequest,
        created_by_user_id: int,
    ) -> Decimal:
        """Post the fixed event entitlement before reserving approved days."""

        code = (
            request.leave_type.code
            if request.leave_type is not None
            else ""
        ).strip().upper()
        entitlement = self.event_leave_entitlement(code)
        if entitlement <= Decimal("0.00"):
            return Decimal("0.00")
        if self._event_grant_already_posted(request):
            return Decimal("0.00")

        self._validate_event_leave_gender_eligibility(
            employee=request.employee,
            leave_type_or_code=request.leave_type,
        )

        if code == "HONEYMOON" and self._honeymoon_request_exists(
            company_id=request.company_id,
            employee_id=request.employee_id,
            exclude_request_id=request.id,
        ):
            raise ValueError(
                "Honeymoon Leave is a one-time five-day benefit and has "
                "already been requested or used by this employee."
            )

        balance = self._ensure_balance(
            company_id=request.company_id,
            employee_id=request.employee_id,
            leave_type=request.leave_type,
            year=request.start_date.year,
            employee=request.employee,
            as_of=self._today(),
        )
        balance.allocated_days = (
            Decimal(balance.allocated_days) + entitlement
        )
        self._sync_credit_table_columns(balance)
        self._validate_nonnegative_balance(balance)
        self.session.add(
            LeaveCreditTransaction(
                company_id=request.company_id,
                employee_id=request.employee_id,
                leave_type_id=request.leave_type_id,
                leave_balance_id=balance.id,
                leave_request_id=request.id,
                created_by_user_id=created_by_user_id,
                transaction_type=EVENT_LEAVE_GRANT_TRANSACTION,
                amount_days=entitlement,
                note=(
                    f"Phase 5 qualifying event grant for "
                    f"{request.public_id}: {entitlement} day(s) of "
                    f"{request.leave_type.name}."
                ),
            )
        )
        return entitlement

    def emergency_allowance_summary(
        self,
        *,
        company_id: int,
        employee_id: int,
        year: int,
    ) -> EmergencyAllowanceSummary:
        """Return annual EL used, reserved, and remaining allowance.

        Emergency Leave has no separate credit bucket. Approved EL days are
        funded from Vacation Leave, while this summary independently enforces
        the maximum three-day annual EL classification.
        """

        used = Decimal("0.00")
        reserved = Decimal("0.00")
        last_updated = None

        for request in self.request_repository.list_employee(
            company_id,
            employee_id,
        ):
            code = (
                request.leave_type.code
                if request.leave_type is not None
                else ""
            ).strip().upper()
            if (
                code != "EMERGENCY"
                or request.start_date.year != int(year)
                or request.status not in EMERGENCY_ACTIVE_STATUSES
            ):
                continue

            paid_days = min(
                EMERGENCY_USAGE_LIMIT,
                self._emergency_paid_days(request),
            )
            posted_days = min(
                paid_days,
                max(
                    Decimal("0.00"),
                    Decimal(
                        request.posted_working_days
                        or Decimal("0.00")
                    ),
                ),
            )
            used += posted_days
            reserved += max(
                Decimal("0.00"),
                paid_days - posted_days,
            )

            candidate = request.updated_at or request.reviewed_at
            if candidate is not None and (
                last_updated is None or candidate > last_updated
            ):
                last_updated = candidate

        committed = min(
            EMERGENCY_USAGE_LIMIT,
            used + reserved,
        )
        return EmergencyAllowanceSummary(
            used_days=used.quantize(Decimal("0.01")),
            reserved_days=reserved.quantize(Decimal("0.01")),
            remaining_days=max(
                Decimal("0.00"),
                EMERGENCY_USAGE_LIMIT - committed,
            ).quantize(Decimal("0.01")),
            last_updated=last_updated,
        )

    def credit_table_rows(
        self,
        *,
        company_id: int,
        employee_id: int,
        year: int,
        balances=None,
    ) -> list[LeaveCreditTableRow]:
        """Build the seven display rows without double-counting EL credits."""

        selected_balances = list(
            balances
            if balances is not None
            else self.list_employee_balances(
                company_id,
                employee_id,
                year,
            )
        )
        emergency = self.emergency_allowance_summary(
            company_id=company_id,
            employee_id=employee_id,
            year=year,
        )
        employee = self.employee_repository.get_with_details(
            company_id=company_id,
            employee_id=employee_id,
        )
        rows: list[LeaveCreditTableRow] = []

        for balance in self.credit_table_balances(selected_balances):
            code = (balance.leave_type.code or "").strip().upper()
            is_applicable = self.is_event_leave_gender_eligible(
                employee=employee,
                leave_type_or_code=balance.leave_type,
            )
            if code == "EMERGENCY":
                updated_at = emergency.last_updated or balance.updated_at
                rows.append(
                    LeaveCreditTableRow(
                        leave_type=balance.leave_type,
                        beginning_credit_days=Decimal("0.00"),
                        credit_days=Decimal("0.00"),
                        adjustment_days=Decimal("0.00"),
                        used_days=emergency.used_days,
                        reserved_days=emergency.reserved_days,
                        available_credits=emergency.remaining_days,
                        converted_to_cash_days=Decimal("0.00"),
                        updated_at=updated_at,
                        is_applicable=True,
                    )
                )
                continue

            actual_available = Decimal(balance.available_credits)
            display_available = actual_available

            # Event-based rows show their fixed policy allowance directly in
            # Available Credits before a grant exists. Once a grant has an
            # active remaining or reserved balance, the row shows the real
            # ledger remainder. Honeymoon automatically returns zero after
            # its one-time benefit has already been requested or used.
            if code in EVENT_LEAVE_CODES:
                preview_allowance = self.event_leave_preview_entitlement(
                    company_id=company_id,
                    employee_id=employee_id,
                    leave_type=balance.leave_type,
                )
                if (
                    actual_available <= Decimal("0.00")
                    and Decimal(balance.reserved_days)
                    <= Decimal("0.00")
                ):
                    display_available = preview_allowance

            rows.append(
                LeaveCreditTableRow(
                    leave_type=balance.leave_type,
                    beginning_credit_days=Decimal(
                        balance.beginning_credit_days
                    ),
                    credit_days=Decimal(balance.credit_days),
                    adjustment_days=Decimal(balance.adjustment_days),
                    used_days=Decimal(balance.used_days),
                    reserved_days=Decimal(balance.reserved_days),
                    available_credits=display_available,
                    converted_to_cash_days=Decimal(
                        balance.converted_to_cash_days
                    ),
                    updated_at=balance.updated_at,
                    is_applicable=is_applicable,
                )
            )

        return rows

    @staticmethod
    def _annual_beginning_credit(
        *,
        leave_type: LeaveType,
        previous_balance: LeaveBalance | None,
    ) -> Decimal:
        """Carry only the prior year's post-conversion available balance.

        ``available_credits`` already excludes amounts recorded in
        ``converted_to_cash_days``. This prevents a converted amount from
        returning as Beginning Credit in a later leave year.
        """

        code = (leave_type.code or "").strip().upper()
        if code not in ANNUAL_ACCRUAL_CODES or previous_balance is None:
            return Decimal("0.00")

        return max(
            Decimal("0.00"),
            Decimal(previous_balance.available_credits),
        ).quantize(Decimal("0.00"))

    @staticmethod
    def _cash_conversion_limit(leave_type: LeaveType) -> Decimal | None:
        """Return the fixed retained limit for SL or VL."""

        code = (leave_type.code or "").strip().upper()
        return CASH_CONVERSION_LIMITS.get(code)

    def _cash_conversion_already_processed(
        self,
        balance: LeaveBalance,
    ) -> bool:
        """Return True when this annual ledger already has its cash marker."""

        count = self.session.scalar(
            select(func.count(LeaveCreditTransaction.id)).where(
                LeaveCreditTransaction.leave_balance_id == balance.id,
                LeaveCreditTransaction.transaction_type
                == CASH_CONVERSION_TRANSACTION,
            )
        )
        return bool(count)

    @staticmethod
    def _opening_cash_conversion_amount(
        *,
        balance: LeaveBalance,
        retained_limit: Decimal,
    ) -> Decimal:
        """Calculate the annual excess using the approved ledger formula.

        Total Before Conversion = Beginning Credit + Credit + Adjustment - Used
        Converted to Cash = max(Total Before Conversion - Limit, 0)

        Reserved days are intentionally excluded from the conversion formula;
        they remain separately deducted from usable credits until the related
        request is approved, rejected, or cancelled.
        """

        total_before_conversion = (
            Decimal(balance.beginning_credit_days)
            + Decimal(balance.credit_days)
            + Decimal(balance.adjustment_days)
            - Decimal(balance.used_days)
        )
        return max(
            Decimal("0.00"),
            total_before_conversion - Decimal(retained_limit),
        ).quantize(Decimal("0.00"))

    def _apply_january_cash_conversion(
        self,
        *,
        balance: LeaveBalance,
        leave_type: LeaveType,
        year: int,
    ) -> Decimal:
        """Apply one immutable January SL/VL cash-conversion calculation.

        A zero-value marker is also stored. This keeps processing idempotent
        and prevents later leave usage or manual adjustments from rewriting
        the January conversion result.
        """

        retained_limit = self._cash_conversion_limit(leave_type)
        if retained_limit is None:
            balance.converted_to_cash_days = Decimal("0.00")
            return Decimal("0.00")

        if self._cash_conversion_already_processed(balance):
            return Decimal(balance.converted_to_cash_days)

        converted = self._opening_cash_conversion_amount(
            balance=balance,
            retained_limit=retained_limit,
        )
        balance.converted_to_cash_days = converted

        self.session.add(
            LeaveCreditTransaction(
                company_id=balance.company_id,
                employee_id=balance.employee_id,
                leave_type_id=balance.leave_type_id,
                leave_balance_id=balance.id,
                transaction_type=CASH_CONVERSION_TRANSACTION,
                # A conversion removes days from the usable credit ledger.
                amount_days=-converted,
                note=(
                    f"January {year} cash conversion: retained limit "
                    f"{retained_limit} day(s); converted excess "
                    f"{converted} day(s)."
                ),
            )
        )
        return converted

    def _enforce_cash_conversion_limit(
        self,
        *,
        balance: LeaveBalance,
        leave_type: LeaveType,
        created_by_user_id: int | None = None,
        source: str = "automatic balance validation",
    ) -> Decimal:
        """Move any current SL/VL excess out of usable credits.

        January processing performs the scheduled annual conversion. This
        additional invariant protects every later write path, including
        manual administrator updates and legacy records created before Phase
        3. It is naturally idempotent because converted days are immediately
        removed from ``calculated_available_credits``.
        """

        retained_limit = self._cash_conversion_limit(leave_type)
        if retained_limit is None:
            return Decimal("0.00")

        current_available = Decimal(
            balance.calculated_available_credits
        ).quantize(Decimal("0.01"))
        excess = max(
            Decimal("0.00"),
            current_available - retained_limit,
        ).quantize(Decimal("0.01"))

        if excess <= Decimal("0.00"):
            return Decimal("0.00")

        balance.converted_to_cash_days = (
            Decimal(balance.converted_to_cash_days) + excess
        ).quantize(Decimal("0.01"))

        self.session.add(
            LeaveCreditTransaction(
                company_id=balance.company_id,
                employee_id=balance.employee_id,
                leave_type_id=balance.leave_type_id,
                leave_balance_id=balance.id,
                created_by_user_id=created_by_user_id,
                transaction_type=(
                    CASH_CONVERSION_LIMIT_ENFORCEMENT_TRANSACTION
                ),
                amount_days=-excess,
                note=(
                    f"{source}: retained limit {retained_limit} day(s); "
                    f"converted excess {excess} day(s)."
                ),
            )
        )
        return excess

    def _sync_balance_beginning_credit(
        self,
        *,
        balance: LeaveBalance,
        leave_type: LeaveType,
        year: int,
    ) -> None:
        """Synchronize the current annual beginning credit non-destructively."""

        previous = self.balance_repository.get_balance(
            company_id=balance.company_id,
            employee_id=balance.employee_id,
            leave_type_id=balance.leave_type_id,
            year=year - 1,
        )
        expected = self._annual_beginning_credit(
            leave_type=leave_type,
            previous_balance=previous,
        )
        current = Decimal(balance.carry_over_days)
        if current == expected:
            return

        difference = expected - current
        balance.carry_over_days = expected
        balance.beginning_credit_days = expected
        self.session.add(
            LeaveCreditTransaction(
                company_id=balance.company_id,
                employee_id=balance.employee_id,
                leave_type_id=balance.leave_type_id,
                leave_balance_id=balance.id,
                transaction_type="january_beginning_credit_update",
                amount_days=difference,
                note=(
                    f"Beginning credit for {year} synchronized from the "
                    f"unused {year - 1} balance; beginning credit is now "
                    f"{expected} day(s)."
                ),
            )
        )

    def _sync_balance_allocation(
        self,
        *,
        balance: LeaveBalance,
        employee: Employee,
        leave_type: LeaveType,
        year: int,
        as_of: date | None = None,
    ) -> None:
        """Synchronize only the automatic allocation portion of a balance."""

        code = (leave_type.code or "").strip().upper()
        if code in EVENT_LEAVE_CODES:
            return

        expected = self.calculate_annual_allocation(
            employee=employee,
            leave_type=leave_type,
            year=year,
            as_of=as_of,
        )
        current = Decimal(balance.allocated_days)
        if expected == current:
            return

        difference = expected - current
        balance.allocated_days = expected
        self._sync_credit_table_columns(balance)
        self.session.add(
            LeaveCreditTransaction(
                company_id=balance.company_id,
                employee_id=balance.employee_id,
                leave_type_id=balance.leave_type_id,
                leave_balance_id=balance.id,
                transaction_type="january_annual_accrual_update",
                amount_days=difference,
                note=(
                    f"January {year} annual accrual recalculated from the "
                    f"employee's completed service years on January 1; "
                    f"credit is now {expected} day(s)."
                ),
            )
        )

    def _ensure_balance(
        self,
        *,
        company_id: int,
        employee_id: int,
        leave_type: LeaveType,
        year: int,
        employee: Employee | None = None,
        as_of: date | None = None,
    ) -> LeaveBalance:
        employee = employee or self.employee_repository.get_with_details(
            company_id=company_id,
            employee_id=employee_id,
        )
        if employee is None:
            raise ValueError("The employee record is unavailable.")

        existing = self.balance_repository.get_balance(
            company_id=company_id,
            employee_id=employee_id,
            leave_type_id=leave_type.id,
            year=year,
        )
        if existing is not None:
            # Historical records remain unchanged. The selected annual ledger
            # is synchronized idempotently to the January rules so databases
            # created by older checkpoints receive the corrected SL/VL credit.
            if year >= self._today().year or as_of is not None:
                self._sync_balance_beginning_credit(
                    balance=existing,
                    leave_type=leave_type,
                    year=year,
                )
                self._sync_balance_allocation(
                    balance=existing,
                    employee=employee,
                    leave_type=leave_type,
                    year=year,
                    as_of=as_of,
                )
            self._normalize_emergency_balance(
                balance=existing,
                leave_type=leave_type,
            )
            self._normalize_event_credit_classification(
                balance=existing,
                leave_type=leave_type,
            )
            self._sync_credit_table_columns(existing)
            self._apply_january_cash_conversion(
                balance=existing,
                leave_type=leave_type,
                year=year,
            )
            self._enforce_cash_conversion_limit(
                balance=existing,
                leave_type=leave_type,
                source="Automatic retained-limit repair",
            )
            self._repair_negative_balance(existing)
            return existing

        previous = self.balance_repository.get_balance(
            company_id=company_id,
            employee_id=employee_id,
            leave_type_id=leave_type.id,
            year=year - 1,
        )
        carry_over = self._annual_beginning_credit(
            leave_type=leave_type,
            previous_balance=previous,
        )

        allocation = self.calculate_annual_allocation(
            employee=employee,
            leave_type=leave_type,
            year=year,
            as_of=as_of,
        )
        balance = LeaveBalance(
            company_id=company_id,
            employee_id=employee_id,
            leave_type_id=leave_type.id,
            year=year,
            allocated_days=allocation,
            carry_over_days=carry_over,
            adjustment_days=Decimal("0.00"),
            used_days=Decimal("0.00"),
            reserved_days=Decimal("0.00"),
            beginning_credit_days=carry_over,
            credit_days=allocation,
            converted_to_cash_days=Decimal("0.00"),
        )
        self.session.add(balance)
        self.session.flush()
        self.session.add(
            LeaveCreditTransaction(
                company_id=company_id,
                employee_id=employee_id,
                leave_type_id=leave_type.id,
                leave_balance_id=balance.id,
                transaction_type="january_annual_accrual",
                amount_days=allocation,
                note=(
                    f"January {year} annual accrual based on completed "
                    "service years as of January 1"
                ),
            )
        )
        if carry_over:
            self.session.add(
                LeaveCreditTransaction(
                    company_id=company_id,
                    employee_id=employee_id,
                    leave_type_id=leave_type.id,
                    leave_balance_id=balance.id,
                    transaction_type="january_beginning_credit",
                    amount_days=carry_over,
                    note=f"Unused SL/VL balance carried from {year - 1}",
                )
            )
        self._apply_january_cash_conversion(
            balance=balance,
            leave_type=leave_type,
            year=year,
        )
        self._enforce_cash_conversion_limit(
            balance=balance,
            leave_type=leave_type,
            source="Automatic retained-limit validation",
        )
        self._validate_nonnegative_balance(balance)
        return balance

    def ensure_current_year_balances(
        self,
        company_id: int,
        year: int | None = None,
    ) -> None:
        """Run idempotent January accrual processing for company employees.

        Accessing the portal safely performs the batch when the selected year
        has not yet been processed. Running it again never duplicates credits.
        """

        selected_year = year or self._today().year
        leave_types = self.ensure_default_leave_types(company_id)
        active_types = [item for item in leave_types if item.is_active]
        employees = [
            employee
            for employee in self.employee_repository.list_with_details(
                company_id
            )
            if employee.employment_status == "employed"
        ]
        for employee in employees:
            for leave_type in active_types:
                self._ensure_balance(
                    company_id=company_id,
                    employee_id=employee.id,
                    leave_type=leave_type,
                    year=selected_year,
                    employee=employee,
                )

        # Automatic app-start processing must persist even when there are no
        # approved leave requests for the reconciliation step to commit.
        self.session.commit()
        self.session.commit()

    def list_leave_types(self, company_id: int, *, active_only: bool = False) -> list[LeaveType]:
        self.ensure_default_leave_types(company_id)
        return self.leave_type_repository.list_company(company_id, active_only=active_only)

    def save_leave_type(self, values: LeaveTypeInput, leave_type_id: int | None = None) -> LeaveType:
        """Create or update leave rules and optionally reallocate balances."""

        existing_code = self.leave_type_repository.get_by_code(values.company_id, values.code)
        existing_name = self.leave_type_repository.get_by_name(values.company_id, values.name)
        if leave_type_id is None:
            if existing_code or existing_name:
                raise ValueError("A leave type with that code or name already exists.")
            leave_type = LeaveType(company_id=values.company_id)
            self.session.add(leave_type)
        else:
            leave_type = self.leave_type_repository.get_by_id(leave_type_id, values.company_id)
            if leave_type is None:
                raise ValueError("The selected leave type is unavailable.")
            if existing_code is not None and existing_code.id != leave_type.id:
                raise ValueError("That leave type code is already used.")
            if existing_name is not None and existing_name.id != leave_type.id:
                raise ValueError("That leave type name is already used.")

        leave_type.code = values.code
        leave_type.name = values.name
        leave_type.annual_credits = values.annual_credits
        leave_type.is_paid = values.is_paid
        leave_type.carry_over_limit = values.carry_over_limit
        # Supporting attachments are replaced by an optional handover
        # plan and optional plan file.
        leave_type.requires_attachment = False
        leave_type.handover_plan_requirement = (
            values.handover_plan_requirement
        )
        leave_type.minimum_notice_days = values.minimum_notice_days
        leave_type.is_active = values.is_active
        self.session.flush()

        if values.apply_annual_credits_to_existing:
            year = self._today().year
            balances = self.balance_repository.list_company_year(
                values.company_id,
                year,
            )
            for balance in balances:
                if balance.leave_type_id != leave_type.id:
                    continue
                self._sync_balance_allocation(
                    balance=balance,
                    employee=balance.employee,
                    leave_type=leave_type,
                    year=year,
                )
        self.session.commit()
        self.session.refresh(leave_type)
        return leave_type

    def list_company_balances(self, company_id: int, year: int | None = None) -> list[LeaveBalance]:
        selected_year = year or self._today().year
        self.ensure_current_year_balances(company_id, selected_year)
        return self.balance_repository.list_company_year(company_id, selected_year)

    def list_employee_balances(self, company_id: int, employee_id: int, year: int | None = None) -> list[LeaveBalance]:
        selected_year = year or self._today().year
        self.ensure_current_year_balances(company_id, selected_year)
        return self.balance_repository.list_employee_year(company_id, employee_id, selected_year)

    def adjust_credit(self, values: LeaveCreditAdjustmentInput) -> LeaveBalance:
        leave_type = self.leave_type_repository.get_by_id(values.leave_type_id, values.company_id)
        employee = self.employee_repository.get_with_details(company_id=values.company_id, employee_id=values.employee_id)
        if leave_type is None or employee is None:
            raise ValueError("The selected employee or leave type is unavailable.")
        selected_code = (leave_type.code or "").strip().upper()
        if selected_code == "EMERGENCY":
            raise ValueError(
                "Emergency Leave has no independent credit balance. Its "
                "three-day annual allowance is automatically deducted from "
                "Vacation Leave."
            )
        if selected_code in EVENT_LEAVE_CODES:
            raise ValueError(
                f"{leave_type.name} credits are created automatically only "
                "after manager approval of a qualifying event request."
            )
        balance = self._ensure_balance(
            company_id=values.company_id,
            employee_id=values.employee_id,
            leave_type=leave_type,
            year=values.year,
        )
        prospective = Decimal(balance.remaining_days) + Decimal(values.adjustment_days)
        if prospective < Decimal("0.00"):
            raise ValueError("The adjustment would make the remaining balance negative.")
        balance.adjustment_days = Decimal(balance.adjustment_days) + Decimal(values.adjustment_days)
        self._sync_credit_table_columns(balance)
        self._enforce_cash_conversion_limit(
            balance=balance,
            leave_type=leave_type,
            created_by_user_id=values.created_by_user_id,
            source="Manual credit adjustment",
        )
        self._validate_nonnegative_balance(balance)
        self.session.add(
            LeaveCreditTransaction(
                company_id=values.company_id,
                employee_id=values.employee_id,
                leave_type_id=values.leave_type_id,
                leave_balance_id=balance.id,
                created_by_user_id=values.created_by_user_id,
                transaction_type="manual_adjustment",
                amount_days=values.adjustment_days,
                note=values.reason,
            )
        )
        self.session.commit()
        self.session.refresh(balance)
        return balance

    def set_credit_balance(
        self,
        values: LeaveCreditBalanceSetInput,
    ) -> LeaveCreditBalanceSetResult:
        """Set credits and automatically cash-convert SL/VL excess.

        The administrator enters the intended usable balance. The service
        preserves Beginning Credit and Credit, then records only the required
        difference in Adjustment. For Sick Leave and Vacation Leave, any
        portion above the fixed retained limit is
        transferred to ``converted_to_cash_days`` during the same database
        transaction. The resulting usable balance therefore never exceeds 15
        SL days or 45 VL days.
        """

        leave_type = self.leave_type_repository.get_by_id(
            values.leave_type_id,
            values.company_id,
        )
        employee = self.employee_repository.get_with_details(
            company_id=values.company_id,
            employee_id=values.employee_id,
        )

        if leave_type is None or employee is None:
            raise ValueError(
                "The selected employee or leave type is unavailable."
            )
        selected_code = (leave_type.code or "").strip().upper()
        if selected_code == "EMERGENCY":
            raise ValueError(
                "Emergency Leave has no independent credit balance. Its "
                "three-day annual allowance is automatically deducted from "
                "Vacation Leave."
            )
        if selected_code in EVENT_LEAVE_CODES:
            raise ValueError(
                f"{leave_type.name} credits are created automatically only "
                "after manager approval of a qualifying event request."
            )

        balance = self._ensure_balance(
            company_id=values.company_id,
            employee_id=values.employee_id,
            leave_type=leave_type,
            year=values.year,
        )

        previous_remaining = Decimal(
            balance.remaining_days
        ).quantize(Decimal("0.01"))
        requested_remaining = Decimal(
            values.new_remaining_days
        ).quantize(Decimal("0.01"))

        retained_limit = self._cash_conversion_limit(leave_type)
        expected_remaining = (
            min(requested_remaining, retained_limit)
            if retained_limit is not None
            else requested_remaining
        ).quantize(Decimal("0.01"))
        expected_conversion = (
            max(
                Decimal("0.00"),
                requested_remaining - retained_limit,
            ).quantize(Decimal("0.01"))
            if retained_limit is not None
            else Decimal("0.00")
        )

        if (
            expected_remaining == previous_remaining
            and expected_conversion == Decimal("0.00")
        ):
            raise ValueError(
                f"{leave_type.name} already has "
                f"{expected_remaining} remaining credits."
            )

        # Apply the requested amount relative to the current usable balance.
        # The invariant below then removes any portion above the retained
        # limit and records it in Converted to Cash.
        internal_difference = (
            requested_remaining - previous_remaining
        )
        balance.adjustment_days = (
            Decimal(balance.adjustment_days)
            + internal_difference
        )
        self._sync_credit_table_columns(balance)

        converted_to_cash = self._enforce_cash_conversion_limit(
            balance=balance,
            leave_type=leave_type,
            created_by_user_id=values.created_by_user_id,
            source="Manual leave credit update",
        )
        self._validate_nonnegative_balance(balance)
        actual_remaining = Decimal(
            balance.remaining_days
        ).quantize(Decimal("0.01"))

        self.session.add(
            LeaveCreditTransaction(
                company_id=values.company_id,
                employee_id=values.employee_id,
                leave_type_id=values.leave_type_id,
                leave_balance_id=balance.id,
                created_by_user_id=values.created_by_user_id,
                transaction_type="manual_balance_set",
                # For this transaction type, amount_days stores the exact
                # resulting usable balance after conversion.
                amount_days=actual_remaining,
                note=(
                    f"Previous balance: {previous_remaining} days | "
                    f"New balance: {actual_remaining} days | "
                    f"Requested credits: {requested_remaining} days | "
                    f"Converted to cash: {converted_to_cash} days"
                ),
            )
        )

        self.session.commit()
        self.session.refresh(balance)

        return LeaveCreditBalanceSetResult(
            balance=balance,
            previous_remaining=previous_remaining,
            requested_remaining=requested_remaining,
            new_remaining=actual_remaining,
            converted_to_cash=converted_to_cash,
        )

    def list_credit_history(self, company_id: int, employee_id: int, year: int | None = None):
        return self.transaction_repository.list_employee_year(company_id, employee_id, year or self._today().year)

    def _admin_cc_emails(self, company_id: int, *, exclude: set[str]) -> list[str]:
        emails: list[str] = []
        for user in self.user_repository.list_with_details(company_id):
            email = (user.email or "").strip()
            if user.is_active and int(user.clearance) == 1 and email and email.lower() not in exclude:
                exclude.add(email.lower())
                emails.append(email)
        return emails

    def _notification_recipients(self, *, company_id: int, employee: Employee, manager: Employee | None) -> set[int]:
        recipients: set[int] = set()
        if employee.user_id:
            recipients.add(employee.user_id)
        if manager is not None and manager.user_id:
            recipients.add(manager.user_id)
        for user in self.user_repository.list_with_details(company_id):
            if user.is_active and int(user.clearance) == 1:
                recipients.add(user.id)
        return recipients

    def _request_allocation_plan(
        self,
        *,
        company_id: int,
        employee: Employee,
        leave_type: LeaveType,
        year: int,
        requested_days: Decimal,
        as_of: date | None = None,
        virtual_primary_credit: Decimal = Decimal("0.00"),
    ) -> LeaveAllocationPlan:
        """Split requested days into paid credits and automatic LWOP."""

        requested = max(Decimal("0.00"), Decimal(requested_days))
        code = (leave_type.code or "").strip().upper()

        if code == "LWOP" or not leave_type.is_paid:
            return LeaveAllocationPlan(
                primary_balance=None,
                primary_days=Decimal("0.00"),
                fallback_balance=None,
                fallback_days=Decimal("0.00"),
                lwop_days=requested,
            )

        primary_balance = self._ensure_balance(
            company_id=company_id,
            employee_id=employee.id,
            leave_type=leave_type,
            year=year,
            employee=employee,
            as_of=as_of,
        )

        if code == "EMERGENCY":
            # The EL row is only an annual three-day usage tracker. Paid EL
            # days are reserved and posted exclusively against Vacation Leave
            # so no additional leave credits are created.
            summary = self.emergency_allowance_summary(
                company_id=company_id,
                employee_id=employee.id,
                year=year,
            )
            vacation_type = self.leave_type_repository.get_by_code(
                company_id,
                "VACATION",
            )
            vacation_balance = None
            vacation_available = Decimal("0.00")

            if vacation_type is not None and vacation_type.is_active:
                vacation_balance = self._ensure_balance(
                    company_id=company_id,
                    employee_id=employee.id,
                    leave_type=vacation_type,
                    year=year,
                    employee=employee,
                    as_of=as_of,
                )
                vacation_available = max(
                    Decimal("0.00"),
                    Decimal(vacation_balance.remaining_days),
                )

            paid_emergency = min(
                requested,
                summary.remaining_days,
                vacation_available,
            )
            return LeaveAllocationPlan(
                primary_balance=primary_balance,
                primary_days=Decimal("0.00"),
                fallback_balance=vacation_balance,
                fallback_days=paid_emergency,
                lwop_days=max(
                    Decimal("0.00"),
                    requested - paid_emergency,
                ),
            )

        primary_available = max(
            Decimal("0.00"),
            Decimal(primary_balance.remaining_days)
            + Decimal(virtual_primary_credit),
        )
        event_limit = self.event_leave_entitlement(code)
        primary_days = min(
            requested,
            primary_available,
            event_limit,
        ) if event_limit > Decimal("0.00") else min(
            requested,
            primary_available,
        )
        remaining = requested - primary_days

        return LeaveAllocationPlan(
            primary_balance=primary_balance,
            primary_days=primary_days,
            fallback_balance=None,
            fallback_days=Decimal("0.00"),
            lwop_days=max(Decimal("0.00"), remaining),
        )

    @staticmethod
    def allocation_breakdown(request: LeaveRequest) -> str:
        """Return a readable paid-credit/LWOP split for tables and email."""

        def format_days(value: Decimal) -> str:
            return f"{value:.2f}".rstrip("0").rstrip(".")

        parts: list[str] = []
        primary_days = Decimal(
            request.primary_credit_days or Decimal("0.00")
        )
        fallback_days = Decimal(
            request.fallback_credit_days or Decimal("0.00")
        )
        lwop_days = Decimal(request.lwop_days or Decimal("0.00"))

        request_code = (
            request.leave_type.code
            if request.leave_type is not None
            else ""
        ).strip().upper()

        if request_code == "EMERGENCY":
            paid_emergency = primary_days + fallback_days
            if paid_emergency > 0:
                parts.append(
                    f"{format_days(paid_emergency)} Emergency Leave "
                    "(deducted from Vacation Leave)"
                )
        else:
            if primary_days > 0:
                parts.append(
                    f"{format_days(primary_days)} {request.leave_type.name}"
                )
            if fallback_days > 0 and request.fallback_leave_type is not None:
                parts.append(
                    f"{format_days(fallback_days)} "
                    f"{request.fallback_leave_type.name}"
                )
        if lwop_days > 0:
            parts.append(f"{format_days(lwop_days)} LWOP")

        return " + ".join(parts) or "No credit allocation"

    def submit_leave_request(
        self,
        values: LeaveRequestInput,
        *,
        plan_filename: str | None = None,
        plan_bytes: bytes | None = None,
        plan_mime_type: str | None = None,
        # Older callers may still use these names.
        attachment_filename: str | None = None,
        attachment_bytes: bytes | None = None,
        attachment_mime_type: str | None = None,
    ) -> LeaveSubmissionResult:
        """Record and email a request without deducting credits yet."""

        if plan_filename is None:
            plan_filename = attachment_filename
        if plan_bytes is None:
            plan_bytes = attachment_bytes
        if plan_mime_type is None:
            plan_mime_type = attachment_mime_type

        employee = self.employee_repository.get_with_details(
            company_id=values.company_id,
            employee_id=values.employee_id,
        )
        leave_type = self.leave_type_repository.get_by_id(
            values.leave_type_id,
            values.company_id,
        )

        if (
            employee is None
            or employee.employment_status != "employed"
        ):
            raise ValueError(
                "The employee record is unavailable for leave requests."
            )

        if employee.user_id != values.requested_by_user_id:
            raise ValueError(
                "The leave request does not belong to the signed-in employee."
            )

        if leave_type is None or not leave_type.is_active:
            raise ValueError(
                "The selected leave type is unavailable."
            )

        selected_code = (leave_type.code or "").strip().upper()
        self._validate_event_leave_gender_eligibility(
            employee=employee,
            leave_type_or_code=leave_type,
        )
        if selected_code == "HONEYMOON" and self._honeymoon_request_exists(
            company_id=values.company_id,
            employee_id=values.employee_id,
        ):
            raise ValueError(
                "Honeymoon Leave is a one-time five-day benefit and has "
                "already been requested or used by this employee."
            )

        manager = employee.manager
        manager_email = self._email_for_employee(manager)

        if manager is None or not manager_email:
            raise ValueError(
                "Assign a manager with a work email before submitting leave."
            )

        requested_days = self._business_days(
            values.start_date,
            values.end_date,
        )

        if requested_days <= 0:
            raise ValueError(
                "The selected dates contain no working days."
            )

        today = self._today()
        notice_days = (
            values.start_date - today
        ).days

        if (
            leave_type.minimum_notice_days > 0
            and notice_days
            < leave_type.minimum_notice_days
        ):
            raise ValueError(
                f"{leave_type.name} requires at least "
                f"{leave_type.minimum_notice_days} days notice."
            )

        # Compute a preview split without reserving credits. Event-based
        # requests include their prospective fixed grant only for preview; the
        # real credit is posted exactly once after manager approval.
        preview_event_credit = self.event_leave_preview_entitlement(
            company_id=values.company_id,
            employee_id=values.employee_id,
            leave_type=leave_type,
        )
        allocation = self._request_allocation_plan(
            company_id=values.company_id,
            employee=employee,
            leave_type=leave_type,
            year=values.start_date.year,
            requested_days=requested_days,
            as_of=today,
            virtual_primary_credit=preview_event_credit,
        )

        requirement = (
            leave_type.handover_plan_requirement
            or "optional"
        ).strip().lower()
        has_plan_text = bool(
            (values.handover_plan or "").strip()
        )
        has_plan_file = bool(plan_bytes)

        if (
            requirement == "required"
            and not has_plan_text
            and not has_plan_file
        ):
            raise ValueError(
                f"{leave_type.name} requires a work handover plan "
                "or a handover plan file."
            )

        plan_storage_path = None

        if plan_bytes:
            if not plan_filename:
                raise ValueError(
                    "The handover plan filename is missing."
                )

            self.storage.validate(
                filename=plan_filename,
                file_bytes=plan_bytes,
                maximum_size_bytes=(
                    self.settings.leave_attachment_max_mb
                    * 1024
                    * 1024
                ),
            )
            plan_storage_path = self.storage.write(
                company_id=values.company_id,
                filename=plan_filename,
                file_bytes=plan_bytes,
            )

        employee_email = self._email_for_employee(employee)
        exclude = {manager_email.lower()}
        cc_emails: list[str] = []

        if (
            employee_email
            and employee_email.lower() not in exclude
        ):
            exclude.add(employee_email.lower())
            cc_emails.append(employee_email)

        cc_emails.extend(
            self._admin_cc_emails(
                values.company_id,
                exclude=exclude,
            )
        )

        request = LeaveRequest(
            company_id=values.company_id,
            employee_id=employee.id,
            leave_type_id=leave_type.id,
            fallback_leave_type=(
                allocation.fallback_balance.leave_type
                if allocation.fallback_balance is not None
                else None
            ),
            manager_employee_id=manager.id,
            start_date=values.start_date,
            end_date=values.end_date,
            requested_days=requested_days,
            primary_credit_days=allocation.primary_days,
            fallback_credit_days=allocation.fallback_days,
            lwop_days=allocation.lwop_days,
            reason=values.reason,
            handover_plan=values.handover_plan,
            status="pending_manager_approval",
            manager_email=manager_email,
            cc_emails_json=json.dumps(cc_emails),
            email_status="pending",
            attachment_original_filename=(
                plan_filename if plan_bytes else None
            ),
            attachment_storage_path=plan_storage_path,
            attachment_mime_type=(
                plan_mime_type if plan_bytes else None
            ),
            attachment_size_bytes=(
                len(plan_bytes) if plan_bytes else None
            ),
            reservation_posted=False,
            posted_working_days=Decimal("0.00"),
        )
        self.session.add(request)

        try:
            self.session.flush()
            request.public_id = (
                f"LRQ_{request.id:06d}"
            )

            for user_id in self._notification_recipients(
                company_id=values.company_id,
                employee=employee,
                manager=manager,
            ):
                if user_id == employee.user_id:
                    title = "Leave request sent"
                    message = (
                        f"{request.public_id} was sent to "
                        f"{manager.full_name}. No credits are deducted "
                        "until manager approval."
                    )
                elif user_id == manager.user_id:
                    title = "Leave request needs approval"
                    message = (
                        f"{employee.full_name} submitted "
                        f"{leave_type.name} for "
                        f"{requested_days} working day(s). "
                        f"Proposed split: {self.allocation_breakdown(request)}. "
                        "Open Leave Management to review it."
                    )
                else:
                    title = "New leave request submitted"
                    message = (
                        f"{employee.full_name} sent "
                        f"{request.public_id} to "
                        f"{manager.full_name}."
                    )

                self.notification_service.create(
                    company_id=values.company_id,
                    user_id=user_id,
                    event_type="leave_request_submitted",
                    title=title,
                    message=message,
                    related_entity_type="leave_request",
                    related_entity_id=request.id,
                )

            self.session.commit()
            self.session.refresh(request)

        except Exception:
            self.session.rollback()
            self.storage.delete(plan_storage_path)
            raise

        attachments: tuple[EmailAttachment, ...] = ()

        if plan_bytes and plan_filename:
            attachments = (
                EmailAttachment(
                    filename=Path(plan_filename).name,
                    content=plan_bytes,
                    mime_type=(
                        plan_mime_type
                        or "application/octet-stream"
                    ),
                ),
            )

        base_url = (
            self.settings.password_reset_base_url
            or "http://localhost:8501"
        ).rstrip("/")
        approval_url = (
            f"{base_url}/?portal=employee"
            "&page=Leave%20Management"
            f"&leave_request_id={request.id}"
        )
        plan_text = (
            values.handover_plan.strip()
            if values.handover_plan
            else "Not provided"
        )

        subject = (
            f"{request.public_id} - "
            f"{employee.full_name} - "
            f"{leave_type.name}"
        )
        body = (
            f"Hello {manager.full_name},\n\n"
            f"{employee.full_name} "
            f"({employee.employee_number}) "
            "submitted a leave request.\n\n"
            f"Request ID: {request.public_id}\n"
            f"Leave Type: {leave_type.name}\n"
            f"Dates: {values.start_date.isoformat()} "
            f"to {values.end_date.isoformat()}\n"
            f"Working Days: {requested_days}\n"
            f"Reason: {values.reason}\n\n"
            "Work Handover Plan / Countermeasure:\n"
            f"{plan_text}\n\n"
            f"Plan File: "
            f"{Path(plan_filename).name if plan_filename else 'None'}\n\n"
            "Review this request in AI HR Assistant:\n"
            f"{approval_url}\n\n"
            "Credits are not deducted while the request is pending. "
            "Approved days become reserved and are posted as used only "
            "when their leave dates occur.\n\n"
            f"CC: "
            f"{', '.join(cc_emails) if cc_emails else 'None'}"
        )

        try:
            reference = self.email_sender.send(
                OutboundEmail(
                    to_email=manager_email,
                    cc_emails=tuple(cc_emails),
                    subject=subject,
                    text_body=body,
                    attachments=attachments,
                )
            )
            request.email_status = "sent"
            request.email_reference = reference
            request.email_error = None
            message = (
                f"Leave request {request.public_id} was sent to "
                f"{manager.full_name} for approval. "
                f"Proposed split: {self.allocation_breakdown(request)}."
            )
            email_sent = True

        except EmailDeliveryError as error:
            request.email_status = "failed"
            request.email_error = str(error)[:500]
            message = (
                f"Leave request {request.public_id} was recorded, "
                "but email delivery failed. The manager can still "
                "review it through Leave Management."
            )
            email_sent = False

        self.session.commit()
        self.session.refresh(request)

        return LeaveSubmissionResult(
            request=request,
            email_sent=email_sent,
            message=message,
        )



    def is_manager(
        self,
        *,
        company_id: int,
        employee_id: int,
    ) -> bool:
        """Return whether an employee has active direct reports."""

        return bool(
            self.employee_repository.list_direct_reports(
                company_id=company_id,
                manager_employee_id=employee_id,
            )
        )

    def list_pending_manager_requests(
        self,
        *,
        company_id: int,
        manager_employee_id: int,
    ) -> list[LeaveRequest]:
        """Return requests awaiting this manager's decision."""

        return self.request_repository.list_pending_for_manager(
            company_id=company_id,
            manager_employee_id=manager_employee_id,
        )

    def list_reviewed_manager_requests(
        self,
        *,
        company_id: int,
        manager_employee_id: int,
    ) -> list[LeaveRequest]:
        """Return requests already reviewed by this manager."""

        return self.request_repository.list_reviewed_for_manager(
            company_id=company_id,
            manager_employee_id=manager_employee_id,
        )

    def _decision_notification_recipients(
        self,
        *,
        company_id: int,
        employee: Employee,
        manager: Employee | None,
    ) -> set[int]:
        """Return employee, manager, and active administrator user IDs."""

        return self._notification_recipients(
            company_id=company_id,
            employee=employee,
            manager=manager,
        )

    def _send_decision_email(
        self,
        *,
        request: LeaveRequest,
        decision_label: str,
    ) -> bool:
        """Email the employee and configured CC recipients after review."""

        employee_email = self._email_for_employee(
            request.employee
        )

        if not employee_email:
            return False

        cc_emails = [
            value
            for value in self.cc_emails(request)
            if value.lower() != employee_email.lower()
        ]
        manager_name = (
            request.manager.full_name
            if request.manager
            else "Assigned Manager"
        )
        comment = (
            request.manager_comment
            or "No manager comment."
        )
        body = (
            f"Hello {request.employee.full_name},\n\n"
            f"Your leave request {request.public_id} was "
            f"{decision_label.lower()} by {manager_name}.\n\n"
            f"Leave Type: {request.leave_type.name}\n"
            f"Dates: {request.start_date.isoformat()} "
            f"to {request.end_date.isoformat()}\n"
            f"Working Days: {request.requested_days}\n"
            f"Manager Comment: {comment}\n\n"
        )

        if decision_label == "Approved":
            body += (
                "Paid days are now reserved and will be posted as used "
                "when the leave dates occur. Any automatic LWOP portion "
                "does not consume leave credits."
            )
        else:
            body += (
                "No leave credits were reserved or deducted."
            )

        try:
            self.email_sender.send(
                OutboundEmail(
                    to_email=employee_email,
                    cc_emails=tuple(cc_emails),
                    subject=(
                        f"{request.public_id} - "
                        f"{decision_label}"
                    ),
                    text_body=body,
                )
            )
            return True
        except EmailDeliveryError:
            return False

    def decide_leave_request(
        self,
        values: LeaveDecisionInput,
    ) -> LeaveRequest:
        """Approve or reject one request as its assigned manager."""

        request = self.request_repository.get_with_details(
            values.company_id,
            values.request_id,
        )

        if request is None:
            raise ValueError(
                "The selected leave request is unavailable."
            )

        if (
            request.manager_employee_id
            != values.manager_employee_id
        ):
            raise ValueError(
                "Only the assigned manager can review this request."
            )

        if (
            request.manager is None
            or request.manager.user_id
            != values.manager_user_id
        ):
            raise ValueError(
                "The signed-in account is not linked to the assigned manager."
            )

        if request.status != "pending_manager_approval":
            raise ValueError(
                "This leave request has already been reviewed."
            )

        if values.decision == "approve":
            self._validate_event_leave_gender_eligibility(
                employee=request.employee,
                leave_type_or_code=request.leave_type,
            )

        now = datetime.now(timezone.utc)
        request.reviewed_at = now
        request.reviewed_by_user_id = values.manager_user_id
        request.manager_comment = values.manager_comment

        if values.decision == "reject":
            request.status = "rejected"
            request.reservation_posted = False
            decision_label = "Rejected"
        else:
            # A manager approval is the qualifying event. Post the fixed
            # event-based entitlement first, then reserve only the covered
            # portion; any excess remains automatic LWOP.
            self._grant_event_leave_entitlement(
                request=request,
                created_by_user_id=values.manager_user_id,
            )
            allocation = self._request_allocation_plan(
                company_id=request.company_id,
                employee=request.employee,
                leave_type=request.leave_type,
                year=request.start_date.year,
                requested_days=Decimal(request.requested_days),
                as_of=self._today(),
            )

            request.fallback_leave_type = (
                allocation.fallback_balance.leave_type
                if allocation.fallback_balance is not None
                else None
            )
            request.primary_credit_days = allocation.primary_days
            request.fallback_credit_days = allocation.fallback_days
            request.lwop_days = allocation.lwop_days
            request.reservation_posted = allocation.paid_days > 0

            reservation_items = (
                (allocation.primary_balance, allocation.primary_days),
                (allocation.fallback_balance, allocation.fallback_days),
            )
            for reserved_balance, reserved_days in reservation_items:
                if reserved_balance is None or reserved_days <= 0:
                    continue

                reserved_balance.reserved_days = (
                    Decimal(reserved_balance.reserved_days)
                    + reserved_days
                )
                self._validate_nonnegative_balance(reserved_balance)
                self.session.add(
                    LeaveCreditTransaction(
                        company_id=request.company_id,
                        employee_id=request.employee_id,
                        leave_type_id=reserved_balance.leave_type_id,
                        leave_balance_id=reserved_balance.id,
                        leave_request_id=request.id,
                        created_by_user_id=values.manager_user_id,
                        transaction_type="approval_reserved",
                        amount_days=-reserved_days,
                        note=(
                            f"Reserved after manager approval for "
                            f"{request.public_id}; automatic split includes "
                            f"{allocation.lwop_days} LWOP day(s)."
                        ),
                    )
                )

            request.approved_at = now
            request.status = (
                "scheduled"
                if request.start_date > self._today()
                else "approved"
            )
            decision_label = "Approved"

        for user_id in self._decision_notification_recipients(
            company_id=request.company_id,
            employee=request.employee,
            manager=request.manager,
        ):
            if user_id == request.employee.user_id:
                title = (
                    f"Leave request {decision_label.lower()}"
                )
                message = (
                    f"{request.public_id} was "
                    f"{decision_label.lower()} by "
                    f"{request.manager.full_name}. "
                    f"Final split: {self.allocation_breakdown(request)}."
                )
            elif user_id == request.manager.user_id:
                title = "Leave decision recorded"
                message = (
                    f"{request.public_id} was "
                    f"{decision_label.lower()}."
                )
            else:
                title = "Leave request reviewed"
                message = (
                    f"{request.manager.full_name} "
                    f"{decision_label.lower()} "
                    f"{request.public_id} for "
                    f"{request.employee.full_name}."
                )

            self.notification_service.create(
                company_id=request.company_id,
                user_id=user_id,
                event_type=(
                    "leave_request_approved"
                    if values.decision == "approve"
                    else "leave_request_rejected"
                ),
                title=title,
                message=message,
                related_entity_type="leave_request",
                related_entity_id=request.id,
            )

        self.session.commit()
        self.session.refresh(request)

        if values.decision == "approve":
            self.reconcile_approved_leave(
                company_id=request.company_id,
                through_date=self._today(),
            )
            request = self.request_repository.get_with_details(
                request.company_id,
                request.id,
            )

        self._send_decision_email(
            request=request,
            decision_label=decision_label,
        )

        return request

    def reconcile_approved_leave(
        self,
        *,
        company_id: int,
        through_date: date | None = None,
    ) -> int:
        """Move elapsed approved days from reserved to used exactly once."""

        selected_date = through_date or self._today()
        requests = self.request_repository.list_reconcilable(
            company_id=company_id,
            through_date=selected_date,
        )
        changed = 0

        for request in requests:
            elapsed_end = min(
                selected_date,
                request.end_date,
            )
            elapsed_days = self._business_days(
                request.start_date,
                elapsed_end,
            )
            already_posted = Decimal(
                request.posted_working_days
                or Decimal("0.00")
            )
            to_post = elapsed_days - already_posted

            if to_post > 0:
                primary_total = Decimal(
                    request.primary_credit_days or Decimal("0.00")
                )
                fallback_total = Decimal(
                    request.fallback_credit_days or Decimal("0.00")
                )

                old_primary = min(already_posted, primary_total)
                new_primary = min(elapsed_days, primary_total)
                primary_to_post = max(
                    Decimal("0.00"),
                    new_primary - old_primary,
                )

                old_fallback = min(
                    max(
                        Decimal("0.00"),
                        already_posted - primary_total,
                    ),
                    fallback_total,
                )
                new_fallback = min(
                    max(
                        Decimal("0.00"),
                        elapsed_days - primary_total,
                    ),
                    fallback_total,
                )
                fallback_to_post = max(
                    Decimal("0.00"),
                    new_fallback - old_fallback,
                )

                posting_items = (
                    (
                        request.leave_type,
                        primary_to_post,
                    ),
                    (
                        request.fallback_leave_type,
                        fallback_to_post,
                    ),
                )
                for posting_type, posting_days in posting_items:
                    if posting_type is None or posting_days <= 0:
                        continue

                    balance = self._ensure_balance(
                        company_id=request.company_id,
                        employee_id=request.employee_id,
                        leave_type=posting_type,
                        year=request.start_date.year,
                        employee=request.employee,
                        as_of=selected_date,
                    )
                    balance.reserved_days = max(
                        Decimal("0.00"),
                        Decimal(balance.reserved_days) - posting_days,
                    )
                    balance.used_days = (
                        Decimal(balance.used_days) + posting_days
                    )
                    self.session.add(
                        LeaveCreditTransaction(
                            company_id=request.company_id,
                            employee_id=request.employee_id,
                            leave_type_id=posting_type.id,
                            leave_balance_id=balance.id,
                            leave_request_id=request.id,
                            transaction_type="leave_days_used",
                            amount_days=-posting_days,
                            note=(
                                f"Posted elapsed approved leave through "
                                f"{elapsed_end.isoformat()} for "
                                f"{request.public_id}"
                            ),
                        )
                    )

                # Total lifecycle progress includes automatic LWOP days even
                # though those days do not touch a credit balance.
                request.posted_working_days = elapsed_days
                changed += 1

            if (
                selected_date >= request.end_date
                and Decimal(request.posted_working_days)
                >= Decimal(request.requested_days)
            ):
                request.status = "completed"
                request.completed_at = datetime.now(
                    timezone.utc
                )
            elif selected_date >= request.start_date:
                request.status = "in_progress"
            else:
                request.status = "scheduled"

        if changed:
            self.session.commit()

        return changed
    def list_company_requests(
        self,
        company_id: int,
        year: int | None = None,
    ):
        """Return monitored requests, optionally filtered by leave year."""

        return self.request_repository.list_company(
            company_id,
            year=year,
        )

    def list_employee_requests(self, company_id: int, employee_id: int):
        return self.request_repository.list_employee(company_id, employee_id)

    def get_request(self, company_id: int, request_id: int):
        return self.request_repository.get_with_details(company_id, request_id)

    @staticmethod
    def cc_emails(request: LeaveRequest) -> list[str]:
        try:
            values = json.loads(request.cc_emails_json or "[]")
            return [str(value) for value in values if str(value).strip()]
        except (TypeError, ValueError, json.JSONDecodeError):
            return []

    def read_plan_file(self, request: LeaveRequest) -> bytes:
        """Read an optional work handover-plan file."""

        if not request.attachment_storage_path:
            raise FileNotFoundError(
                "This leave request has no handover plan file."
            )
        return self.storage.read(
            request.attachment_storage_path
        )

    def read_attachment(self, request: LeaveRequest) -> bytes:
        """Backward-compatible alias for older admin pages."""

        return self.read_plan_file(request)

    def overview(
        self,
        company_id: int,
        year: int | None = None,
    ) -> dict[str, int]:
        """Return summary metrics for the selected Leave Year."""

        today = self._today()
        selected_year = int(year or today.year)
        requests = self.list_company_requests(
            company_id,
            selected_year,
        )
        submitted_in_year = [
            request
            for request in requests
            if (
                request.submitted_at
                and request.submitted_at.year
                == selected_year
            )
        ]
        current_month = [
            request
            for request in requests
            if (
                selected_year == today.year
                and request.submitted_at
                and request.submitted_at.year == today.year
                and request.submitted_at.month == today.month
            )
        ]
        on_leave_today = [
            request
            for request in requests
            if (
                selected_year == today.year
                and request.status in {
                    "scheduled",
                    "approved",
                    "in_progress",
                    "completed",
                }
                and request.start_date <= today <= request.end_date
            )
        ]
        balances = self.list_company_balances(
            company_id,
            selected_year,
        )
        low_employee_ids = {
            balance.employee_id
            for balance in balances
            if (
                balance.leave_type.annual_credits > 0
                and Decimal(balance.remaining_days)
                <= Decimal("2.00")
            )
        }
        employees_with_leave = {
            request.employee_id
            for request in requests
        }

        # Existing keys remain for compatibility with previous callers.
        return {
            "total_requests": len(requests),
            "requests_this_month": len(current_month),
            "requests_submitted_in_year": len(
                submitted_in_year
            ),
            "employees_on_leave_today": len(
                {
                    request.employee_id
                    for request in on_leave_today
                }
            ),
            "employees_with_leave": len(
                employees_with_leave
            ),
            "employees_with_low_credits": len(
                low_employee_ids
            ),
        }
