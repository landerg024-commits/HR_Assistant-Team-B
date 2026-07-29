"""Leave credits, requests, manager email delivery, and HR monitoring."""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
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
        "code": "VACATION",
        "name": "Vacation Leave",
        "annual_credits": Decimal("15.00"),
        "is_paid": True,
        "carry_over_limit": Decimal("5.00"),
        "requires_attachment": False,
        "minimum_notice_days": 5,
        "handover_plan_requirement": "recommended",
    },
    {
        "code": "SICK",
        "name": "Sick Leave",
        "annual_credits": Decimal("10.00"),
        "is_paid": True,
        "carry_over_limit": Decimal("0.00"),
        "requires_attachment": False,
        "minimum_notice_days": 0,
        "handover_plan_requirement": "optional",
    },
    {
        "code": "EMERGENCY",
        "name": "Emergency Leave",
        "annual_credits": Decimal("3.00"),
        "is_paid": True,
        "carry_over_limit": Decimal("0.00"),
        "requires_attachment": False,
        "minimum_notice_days": 0,
        "handover_plan_requirement": "optional",
    },
    {
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


@dataclass(frozen=True, slots=True)
class LeaveCreditBalanceSetResult:
    """Outcome after setting an exact remaining leave-credit value."""

    balance: LeaveBalance
    previous_remaining: Decimal
    new_remaining: Decimal


@dataclass(frozen=True, slots=True)
class LeaveSubmissionResult:
    """Outcome returned after recording and emailing a request."""

    request: LeaveRequest
    email_sent: bool
    message: str


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

    def ensure_default_leave_types(self, company_id: int) -> list[LeaveType]:
        """Create missing default types without changing existing settings."""

        changed = False
        for spec in DEFAULT_LEAVE_TYPES:
            existing = self.leave_type_repository.get_by_code(company_id, spec["code"])
            if existing is None:
                self.session.add(LeaveType(company_id=company_id, is_active=True, **spec))
                changed = True
        if changed:
            self.session.commit()
        return self.leave_type_repository.list_company(company_id)

    def _ensure_balance(self, *, company_id: int, employee_id: int, leave_type: LeaveType, year: int) -> LeaveBalance:
        existing = self.balance_repository.get_balance(
            company_id=company_id,
            employee_id=employee_id,
            leave_type_id=leave_type.id,
            year=year,
        )
        if existing is not None:
            return existing

        carry_over = Decimal("0.00")
        previous = self.balance_repository.get_balance(
            company_id=company_id,
            employee_id=employee_id,
            leave_type_id=leave_type.id,
            year=year - 1,
        )
        if previous is not None:
            carry_over = min(
                max(Decimal("0.00"), Decimal(previous.remaining_days)),
                Decimal(leave_type.carry_over_limit),
            )

        balance = LeaveBalance(
            company_id=company_id,
            employee_id=employee_id,
            leave_type_id=leave_type.id,
            year=year,
            allocated_days=Decimal(leave_type.annual_credits),
            carry_over_days=carry_over,
            adjustment_days=Decimal("0.00"),
            used_days=Decimal("0.00"),
            reserved_days=Decimal("0.00"),
        )
        self.session.add(balance)
        self.session.flush()
        self.session.add(
            LeaveCreditTransaction(
                company_id=company_id,
                employee_id=employee_id,
                leave_type_id=leave_type.id,
                leave_balance_id=balance.id,
                transaction_type="annual_allocation",
                amount_days=Decimal(leave_type.annual_credits),
                note=f"Annual {year} allocation",
            )
        )
        if carry_over:
            self.session.add(
                LeaveCreditTransaction(
                    company_id=company_id,
                    employee_id=employee_id,
                    leave_type_id=leave_type.id,
                    leave_balance_id=balance.id,
                    transaction_type="carry_over",
                    amount_days=carry_over,
                    note=f"Carry-over from {year - 1}",
                )
            )
        return balance

    def ensure_current_year_balances(self, company_id: int, year: int | None = None) -> None:
        """Create current-year balances for all employed employees."""

        selected_year = year or self._today().year
        leave_types = self.ensure_default_leave_types(company_id)
        active_types = [item for item in leave_types if item.is_active]
        employees = [
            employee
            for employee in self.employee_repository.list_with_details(company_id)
            if employee.employment_status == "employed"
        ]
        for employee in employees:
            for leave_type in active_types:
                self._ensure_balance(
                    company_id=company_id,
                    employee_id=employee.id,
                    leave_type=leave_type,
                    year=selected_year,
                )
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
            balances = self.balance_repository.list_company_year(values.company_id, year)
            for balance in balances:
                if balance.leave_type_id == leave_type.id:
                    difference = Decimal(values.annual_credits) - Decimal(balance.allocated_days)
                    balance.allocated_days = values.annual_credits
                    if difference:
                        self.session.add(
                            LeaveCreditTransaction(
                                company_id=values.company_id,
                                employee_id=balance.employee_id,
                                leave_type_id=leave_type.id,
                                leave_balance_id=balance.id,
                                transaction_type="allocation_update",
                                amount_days=difference,
                                note=f"Annual allocation changed to {values.annual_credits}",
                            )
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
        """Set the exact remaining credits instead of adding a delta.

        The stored adjustment component is recalculated internally so the
        public remaining balance exactly matches ``new_remaining_days``.
        Annual allocation, carry-over, used days, and reserved days remain
        unchanged.
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

        balance = self._ensure_balance(
            company_id=values.company_id,
            employee_id=values.employee_id,
            leave_type=leave_type,
            year=values.year,
        )

        previous_remaining = Decimal(
            balance.remaining_days
        ).quantize(Decimal("0.01"))
        new_remaining = Decimal(
            values.new_remaining_days
        ).quantize(Decimal("0.01"))

        if new_remaining == previous_remaining:
            raise ValueError(
                f"{leave_type.name} already has "
                f"{new_remaining} remaining credits."
            )

        internal_difference = (
            new_remaining - previous_remaining
        )

        balance.adjustment_days = (
            Decimal(balance.adjustment_days)
            + internal_difference
        )

        self.session.add(
            LeaveCreditTransaction(
                company_id=values.company_id,
                employee_id=values.employee_id,
                leave_type_id=values.leave_type_id,
                leave_balance_id=balance.id,
                created_by_user_id=values.created_by_user_id,
                transaction_type="manual_balance_set",
                # For this transaction type, amount_days stores the exact
                # resulting balance rather than a signed adjustment.
                amount_days=new_remaining,
                note=(
                    f"Previous balance: {previous_remaining} days | "
                    f"New balance: {new_remaining} days"
                ),
            )
        )

        self.session.commit()
        self.session.refresh(balance)

        return LeaveCreditBalanceSetResult(
            balance=balance,
            previous_remaining=previous_remaining,
            new_remaining=new_remaining,
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

        balance = self._ensure_balance(
            company_id=values.company_id,
            employee_id=employee.id,
            leave_type=leave_type,
            year=values.start_date.year,
        )

        # Submission only validates availability. The requested days are not
        # reserved until the assigned manager approves the request.
        if (
            Decimal(leave_type.annual_credits) > 0
            and Decimal(balance.remaining_days)
            < requested_days
        ):
            raise ValueError(
                f"Insufficient {leave_type.name} credits. "
                f"Available: {balance.remaining_days}."
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
            manager_employee_id=manager.id,
            start_date=values.start_date,
            end_date=values.end_date,
            requested_days=requested_days,
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
                f"{manager.full_name} for approval."
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
                "The approved days are now reserved. They will be "
                "posted as used credits only when the leave dates occur."
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

        now = datetime.now(timezone.utc)
        request.reviewed_at = now
        request.reviewed_by_user_id = values.manager_user_id
        request.manager_comment = values.manager_comment

        if values.decision == "reject":
            request.status = "rejected"
            request.reservation_posted = False
            decision_label = "Rejected"
        else:
            balance = self._ensure_balance(
                company_id=request.company_id,
                employee_id=request.employee_id,
                leave_type=request.leave_type,
                year=request.start_date.year,
            )

            if (
                Decimal(request.leave_type.annual_credits) > 0
                and Decimal(balance.remaining_days)
                < Decimal(request.requested_days)
            ):
                raise ValueError(
                    f"Insufficient {request.leave_type.name} credits "
                    "at approval time."
                )

            if Decimal(request.leave_type.annual_credits) > 0:
                balance.reserved_days = (
                    Decimal(balance.reserved_days)
                    + Decimal(request.requested_days)
                )
                request.reservation_posted = True

                self.session.add(
                    LeaveCreditTransaction(
                        company_id=request.company_id,
                        employee_id=request.employee_id,
                        leave_type_id=request.leave_type_id,
                        leave_balance_id=balance.id,
                        leave_request_id=request.id,
                        created_by_user_id=values.manager_user_id,
                        transaction_type="approval_reserved",
                        amount_days=-Decimal(
                            request.requested_days
                        ),
                        note=(
                            f"Reserved after manager approval "
                            f"for {request.public_id}"
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
                    f"{request.manager.full_name}."
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

            if (
                to_post > 0
                and request.reservation_posted
                and Decimal(
                    request.leave_type.annual_credits
                ) > 0
            ):
                balance = self._ensure_balance(
                    company_id=request.company_id,
                    employee_id=request.employee_id,
                    leave_type=request.leave_type,
                    year=request.start_date.year,
                )
                balance.reserved_days = max(
                    Decimal("0.00"),
                    Decimal(balance.reserved_days)
                    - to_post,
                )
                balance.used_days = (
                    Decimal(balance.used_days)
                    + to_post
                )
                request.posted_working_days = elapsed_days

                self.session.add(
                    LeaveCreditTransaction(
                        company_id=request.company_id,
                        employee_id=request.employee_id,
                        leave_type_id=request.leave_type_id,
                        leave_balance_id=balance.id,
                        leave_request_id=request.id,
                        transaction_type="leave_days_used",
                        amount_days=-to_post,
                        note=(
                            f"Posted elapsed approved leave through "
                            f"{elapsed_end.isoformat()} for "
                            f"{request.public_id}"
                        ),
                    )
                )
                changed += 1

            elif (
                to_post > 0
                and Decimal(
                    request.leave_type.annual_credits
                ) <= 0
            ):
                # Unpaid/non-credit leave still advances its lifecycle.
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
