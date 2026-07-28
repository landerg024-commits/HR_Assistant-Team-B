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
    },
    {
        "code": "SICK",
        "name": "Sick Leave",
        "annual_credits": Decimal("10.00"),
        "is_paid": True,
        "carry_over_limit": Decimal("0.00"),
        "requires_attachment": False,
        "minimum_notice_days": 0,
    },
    {
        "code": "EMERGENCY",
        "name": "Emergency Leave",
        "annual_credits": Decimal("3.00"),
        "is_paid": True,
        "carry_over_limit": Decimal("0.00"),
        "requires_attachment": False,
        "minimum_notice_days": 0,
    },
    {
        "code": "LWOP",
        "name": "Leave Without Pay",
        "annual_credits": Decimal("0.00"),
        "is_paid": False,
        "carry_over_limit": Decimal("0.00"),
        "requires_attachment": False,
        "minimum_notice_days": 0,
    },
)


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
        leave_type.requires_attachment = values.requires_attachment
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

    def submit_leave_request(self, values: LeaveRequestInput, *, attachment_filename: str | None = None, attachment_bytes: bytes | None = None, attachment_mime_type: str | None = None) -> LeaveSubmissionResult:
        """Record a request, reserve credits, notify users, and email the manager."""

        employee = self.employee_repository.get_with_details(company_id=values.company_id, employee_id=values.employee_id)
        leave_type = self.leave_type_repository.get_by_id(values.leave_type_id, values.company_id)
        if employee is None or employee.employment_status != "employed":
            raise ValueError("The employee record is unavailable for leave requests.")
        if employee.user_id != values.requested_by_user_id:
            raise ValueError("The leave request does not belong to the signed-in employee.")
        if leave_type is None or not leave_type.is_active:
            raise ValueError("The selected leave type is unavailable.")

        manager = employee.manager
        manager_email = self._email_for_employee(manager)
        if manager is None or not manager_email:
            raise ValueError("Assign a manager with a work email before submitting leave.")

        requested_days = self._business_days(values.start_date, values.end_date)
        if requested_days <= 0:
            raise ValueError("The selected dates contain no working days.")

        today = self._today()
        notice_days = (values.start_date - today).days
        if leave_type.minimum_notice_days > 0 and notice_days < leave_type.minimum_notice_days:
            raise ValueError(
                f"{leave_type.name} requires at least {leave_type.minimum_notice_days} days notice."
            )

        balance = self._ensure_balance(
            company_id=values.company_id,
            employee_id=employee.id,
            leave_type=leave_type,
            year=values.start_date.year,
        )
        if leave_type.annual_credits > 0 and Decimal(balance.remaining_days) < requested_days:
            raise ValueError(
                f"Insufficient {leave_type.name} credits. Available: {balance.remaining_days}."
            )

        attachment_storage_path = None
        if leave_type.requires_attachment and not attachment_bytes:
            raise ValueError(f"{leave_type.name} requires a supporting attachment.")
        if attachment_bytes:
            if not attachment_filename:
                raise ValueError("The attachment filename is missing.")
            self.storage.validate(
                filename=attachment_filename,
                file_bytes=attachment_bytes,
                maximum_size_bytes=self.settings.leave_attachment_max_mb * 1024 * 1024,
            )
            attachment_storage_path = self.storage.write(
                company_id=values.company_id,
                filename=attachment_filename,
                file_bytes=attachment_bytes,
            )

        employee_email = self._email_for_employee(employee)
        exclude = {manager_email.lower()}
        cc_emails: list[str] = []
        if employee_email and employee_email.lower() not in exclude:
            exclude.add(employee_email.lower())
            cc_emails.append(employee_email)
        cc_emails.extend(self._admin_cc_emails(values.company_id, exclude=exclude))

        request = LeaveRequest(
            company_id=values.company_id,
            employee_id=employee.id,
            leave_type_id=leave_type.id,
            manager_employee_id=manager.id,
            start_date=values.start_date,
            end_date=values.end_date,
            requested_days=requested_days,
            reason=values.reason,
            status="sent_to_manager",
            manager_email=manager_email,
            cc_emails_json=json.dumps(cc_emails),
            email_status="pending",
            attachment_original_filename=attachment_filename if attachment_bytes else None,
            attachment_storage_path=attachment_storage_path,
            attachment_mime_type=attachment_mime_type if attachment_bytes else None,
            attachment_size_bytes=len(attachment_bytes) if attachment_bytes else None,
        )
        self.session.add(request)
        try:
            self.session.flush()
            request.public_id = f"LRQ_{request.id:06d}"
            balance.reserved_days = Decimal(balance.reserved_days) + requested_days
            self.session.add(
                LeaveCreditTransaction(
                    company_id=values.company_id,
                    employee_id=employee.id,
                    leave_type_id=leave_type.id,
                    leave_balance_id=balance.id,
                    leave_request_id=request.id,
                    created_by_user_id=values.requested_by_user_id,
                    transaction_type="request_reserved",
                    amount_days=-requested_days,
                    note=f"Reserved for {request.public_id}",
                )
            )

            for user_id in self._notification_recipients(company_id=values.company_id, employee=employee, manager=manager):
                if user_id == employee.user_id:
                    title = "Leave request sent"
                    message = f"{request.public_id} was sent to {manager.full_name}."
                elif user_id == manager.user_id:
                    title = "New leave request"
                    message = f"{employee.full_name} submitted {leave_type.name} for {requested_days} working day(s)."
                else:
                    title = "New leave request submitted"
                    message = f"{employee.full_name} sent {request.public_id} to {manager.full_name}."
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
            self.storage.delete(attachment_storage_path)
            raise

        attachments: tuple[EmailAttachment, ...] = ()
        if attachment_bytes and attachment_filename:
            attachments = (
                EmailAttachment(
                    filename=Path(attachment_filename).name,
                    content=attachment_bytes,
                    mime_type=attachment_mime_type or "application/octet-stream",
                ),
            )

        subject = f"{request.public_id} - {employee.full_name} - {leave_type.name}"
        body = (
            f"Hello {manager.full_name},\n\n"
            f"{employee.full_name} ({employee.employee_number}) submitted a leave request.\n\n"
            f"Request ID: {request.public_id}\n"
            f"Leave Type: {leave_type.name}\n"
            f"Dates: {values.start_date.isoformat()} to {values.end_date.isoformat()}\n"
            f"Working Days: {requested_days}\n"
            f"Reason: {values.reason}\n\n"
            "The request is recorded in AI HR Assistant for HR monitoring. "
            "Manager approval is handled through your department process; "
            "there is no HR Admin approve/reject action in the portal.\n\n"
            f"CC: {', '.join(cc_emails) if cc_emails else 'None'}"
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
            message = f"Leave request {request.public_id} was sent to {manager.full_name}."
            email_sent = True
        except EmailDeliveryError as error:
            request.email_status = "failed"
            request.email_error = str(error)[:500]
            message = (
                f"Leave request {request.public_id} was recorded, but email delivery failed. "
                "HR can view the request and email status."
            )
            email_sent = False

        self.session.commit()
        self.session.refresh(request)
        return LeaveSubmissionResult(request=request, email_sent=email_sent, message=message)

    def list_company_requests(self, company_id: int):
        return self.request_repository.list_company(company_id)

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

    def read_attachment(self, request: LeaveRequest) -> bytes:
        if not request.attachment_storage_path:
            raise FileNotFoundError("This leave request has no attachment.")
        return self.storage.read(request.attachment_storage_path)

    def overview(self, company_id: int) -> dict[str, int]:
        requests = self.list_company_requests(company_id)
        today = self._today()
        current_month = [r for r in requests if r.submitted_at and r.submitted_at.year == today.year and r.submitted_at.month == today.month]
        on_leave_today = [r for r in requests if r.start_date <= today <= r.end_date]
        balances = self.list_company_balances(company_id, today.year)
        low_employee_ids = {b.employee_id for b in balances if b.leave_type.annual_credits > 0 and Decimal(b.remaining_days) <= Decimal("2.00")}
        return {
            "total_requests": len(requests),
            "requests_this_month": len(current_month),
            "employees_on_leave_today": len({r.employee_id for r in on_leave_today}),
            "employees_with_low_credits": len(low_employee_ids),
        }
