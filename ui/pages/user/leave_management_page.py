"""Employee requests, manager approvals, and leave-credit status."""

from datetime import date
from decimal import Decimal

from pydantic import ValidationError
import streamlit as st

from authentication.current_user import AuthenticatedUser
from config.settings import get_settings
from database.session import SessionFactory
from schemas.leave_schema import (
    LeaveDecisionInput,
    LeaveRequestInput,
)
from services.leave_service import LeaveService
from ui.components.data_table import render_admin_table
from ui.components.operation_feedback import (
    render_operation_feedback,
    set_operation_feedback,
)


_LEAVE_FORM_NONCE_KEY = "_employee_leave_form_nonce"
_APPROVAL_STATUSES = {
    "scheduled",
    "approved",
    "in_progress",
    "completed",
}


def _days(value) -> str:
    """Format leave days without unnecessary decimal zeros."""

    return (
        f"{Decimal(value):.2f}"
        .rstrip("0")
        .rstrip(".")
    )


def _status(value: str) -> str:
    """Convert a stored workflow status into a readable label."""

    labels = {
        "pending_manager_approval": "Pending Manager Approval",
        "scheduled": "Approved / Scheduled",
        "approved": "Approved",
        "in_progress": "In Progress",
        "completed": "Completed",
        "rejected": "Rejected",
    }
    return labels.get(
        value,
        value.replace("_", " ").title(),
    )


def _nonce() -> int:
    """Return the current request-form nonce."""

    value = int(
        st.session_state.get(
            _LEAVE_FORM_NONCE_KEY,
            0,
        )
    )
    st.session_state[_LEAVE_FORM_NONCE_KEY] = value
    return value


def _key(nonce: int, name: str) -> str:
    """Create one resettable request-form widget key."""

    return f"employee_leave_{nonce}_{name}"


def _render_balances(
    current_user: AuthenticatedUser,
) -> None:
    """Show credits after approved reservations and elapsed leave posting."""

    if current_user.employee_id is None:
        st.warning(
            "Your login account is not linked to an employee record."
        )
        return

    with SessionFactory() as session:
        service = LeaveService(session)
        service.reconcile_approved_leave(
            company_id=current_user.company_id
        )
        balances = service.list_employee_balances(
            current_user.company_id,
            current_user.employee_id,
        )

    if not balances:
        st.info("No leave credits are configured.")
        return

    columns = st.columns(
        min(4, len(balances))
    )

    for column, balance in zip(
        columns,
        balances[:4],
    ):
        with column:
            st.metric(
                balance.leave_type.name,
                _days(balance.remaining_days),
                delta=(
                    f"{_days(balance.reserved_days)} reserved"
                    if Decimal(balance.reserved_days) > 0
                    else None
                ),
            )

    render_admin_table(
        [
            {
                "Leave Type": balance.leave_type.name,
                "Annual Allocation": _days(
                    balance.allocated_days
                ),
                "Carry Over": _days(
                    balance.carry_over_days
                ),
                "Available Credits": _days(
                    balance.remaining_days
                ),
                "Reserved Approved Leave": _days(
                    balance.reserved_days
                ),
                "Used Credits": _days(
                    balance.used_days
                ),
            }
            for balance in balances
        ],
        key="employee-leave-balances",
        min_width=1050,
        column_widths=(
            "210px",
            "150px",
            "110px",
            "145px",
            "180px",
            "120px",
        ),
    )

    st.caption(
        "Pending requests do not affect credits. Approved requests reduce "
        "available credits through reservation. Reserved days become used "
        "only when their approved leave dates occur."
    )


def _load_request_context(
    current_user: AuthenticatedUser,
):
    """Load detached form data used by the email-style request composer."""

    with SessionFactory() as session:
        service = LeaveService(session)
        balances = service.list_employee_balances(
            current_user.company_id,
            current_user.employee_id,
        )
        employee = service.employee_repository.get_with_details(
            company_id=current_user.company_id,
            employee_id=current_user.employee_id,
        )
        admin_emails = service._admin_cc_emails(
            current_user.company_id,
            exclude=set(),
        )

    return balances, employee, admin_emails


def _render_submit(
    current_user: AuthenticatedUser,
) -> None:
    """Render an email-style structured leave-request composer."""

    if current_user.employee_id is None:
        st.warning(
            "Your login account is not linked to an employee record."
        )
        return

    settings = get_settings()
    nonce = _nonce()
    balances, employee, admin_emails = _load_request_context(
        current_user
    )

    if employee is None:
        st.error("Your employee record is unavailable.")
        return

    manager = employee.manager
    manager_email = LeaveService._email_for_employee(
        manager
    )

    if manager is None or not manager_email:
        st.error(
            "A manager with a work email must be assigned before "
            "you can file leave."
        )
        return

    employee_email = LeaveService._email_for_employee(
        employee
    )
    cc_values = []

    if employee_email:
        cc_values.append(employee_email)

    cc_values.extend(
        email
        for email in admin_emails
        if email not in cc_values
        and email.lower() != manager_email.lower()
    )

    st.markdown("### File Leave Request")
    st.caption(
        "Complete the structured request below. To and CC recipients "
        "come from connected employee and administrator records."
    )

    recipient_left, recipient_right = st.columns(2)

    with recipient_left:
        st.text_input(
            "To",
            value=(
                f"{manager.full_name} <{manager_email}>"
            ),
            disabled=True,
            key=_key(nonce, "to"),
        )

    with recipient_right:
        st.text_area(
            "CC",
            value=(
                "\n".join(cc_values)
                if cc_values
                else "No automatic CC recipient"
            ),
            disabled=True,
            height=92,
            key=_key(nonce, "cc"),
        )

    type_options = {
        balance.leave_type_id: balance
        for balance in balances
        if balance.leave_type.is_active
    }

    if not type_options:
        st.info("No active leave type is available.")
        return

    leave_type_id = st.selectbox(
        "Leave Type *",
        options=list(type_options),
        format_func=lambda value: (
            f"{type_options[value].leave_type.name} · "
            f"{_days(type_options[value].remaining_days)} "
            "available"
        ),
        key=_key(nonce, "type"),
    )
    selected_balance = type_options[leave_type_id]
    selected_type = selected_balance.leave_type

    available_column, rule_column = st.columns(2)

    with available_column:
        st.metric(
            "Available Credits",
            _days(selected_balance.remaining_days),
        )

    with rule_column:
        st.metric(
            "Handover Plan",
            (
                selected_type.handover_plan_requirement
                or "optional"
            ).title(),
        )

    date_left, date_right = st.columns(2)

    with date_left:
        start = st.date_input(
            "Start Date *",
            value=date.today(),
            key=_key(nonce, "start"),
        )

    with date_right:
        end = st.date_input(
            "End Date *",
            value=date.today(),
            key=_key(nonce, "end"),
        )

    working_days = LeaveService.calculate_working_days(
        start,
        end,
    )
    st.info(
        f"Working Days: {_days(working_days)} · "
        "Monday to Friday only."
    )

    reason = st.text_area(
        "Reason *",
        height=130,
        max_chars=4000,
        key=_key(nonce, "reason"),
    )

    plan_requirement = (
        selected_type.handover_plan_requirement
        or "optional"
    ).lower()
    plan_label = (
        "Work Handover Plan / Countermeasure"
        + (
            " *"
            if plan_requirement == "required"
            else " (Optional)"
        )
    )
    handover_plan = st.text_area(
        plan_label,
        height=190,
        max_chars=10000,
        placeholder=(
            "Example:\n"
            "Day 1 — Backup person and pending task\n"
            "Day 2 — Expected action and escalation contact\n"
            "Possible issue — Countermeasure"
        ),
        key=_key(nonce, "plan"),
    )

    plan_file = st.file_uploader(
        "Optional Handover Plan File",
        type=[
            "pdf",
            "docx",
            "xlsx",
            "csv",
            "txt",
        ],
        help=(
            f"Maximum {settings.leave_attachment_max_mb} MB. "
            "Use this for a detailed daily plan or task handover."
        ),
        key=_key(nonce, "plan_file"),
    )

    if (
        plan_requirement == "recommended"
        and not handover_plan.strip()
        and plan_file is None
    ):
        st.warning(
            f"A handover plan is recommended for "
            f"{selected_type.name}, but it is not required."
        )

    submitted = st.button(
        "Send Leave Request to Manager",
        type="primary",
        use_container_width=True,
        key=_key(nonce, "send"),
    )

    if not submitted:
        return

    try:
        values = LeaveRequestInput(
            company_id=current_user.company_id,
            employee_id=current_user.employee_id,
            requested_by_user_id=current_user.user_id,
            leave_type_id=leave_type_id,
            start_date=start,
            end_date=end,
            reason=reason,
            handover_plan=handover_plan,
        )

        with st.spinner(
            "Recording the request and emailing your manager…"
        ):
            with SessionFactory() as session:
                result = LeaveService(
                    session
                ).submit_leave_request(
                    values,
                    plan_filename=(
                        plan_file.name
                        if plan_file
                        else None
                    ),
                    plan_bytes=(
                        plan_file.getvalue()
                        if plan_file
                        else None
                    ),
                    plan_mime_type=(
                        plan_file.type
                        if plan_file
                        else None
                    ),
                )

        st.session_state[
            _LEAVE_FORM_NONCE_KEY
        ] = nonce + 1

        set_operation_feedback(
            result.message,
            namespace="leave_employee",
            level=(
                "success"
                if result.email_sent
                else "warning"
            ),
        )
        st.rerun()

    except (
        ValidationError,
        ValueError,
    ) as error:
        st.error(str(error))

    except Exception:
        st.error(
            "The leave request could not be processed."
        )


def _request_rows(requests):
    """Build employee request-history rows."""

    return [
        {
            "Request ID": request.public_id,
            "Leave Type": request.leave_type.name,
            "Leave Dates": (
                f"{request.start_date.isoformat()} to "
                f"{request.end_date.isoformat()}"
            ),
            "Days": _days(request.requested_days),
            "Manager": (
                request.manager.full_name
                if request.manager
                else "—"
            ),
            "Status": _status(request.status),
            "Plan": (
                "Text + File"
                if request.handover_plan
                and request.attachment_storage_path
                else "Text"
                if request.handover_plan
                else "File"
                if request.attachment_storage_path
                else "None"
            ),
            "Reason": request.reason,
        }
        for request in requests
    ]


def _render_requests(
    current_user: AuthenticatedUser,
) -> None:
    """Render the employee's complete request history."""

    if current_user.employee_id is None:
        st.warning(
            "Your login account is not linked to an employee record."
        )
        return

    with SessionFactory() as session:
        service = LeaveService(session)
        service.reconcile_approved_leave(
            company_id=current_user.company_id
        )
        requests = service.list_employee_requests(
            current_user.company_id,
            current_user.employee_id,
        )

    if not requests:
        st.info(
            "You have not submitted a leave request yet."
        )
        return

    render_admin_table(
        _request_rows(requests),
        key="employee-leave-requests",
        min_width=1450,
        column_widths=(
            "125px",
            "160px",
            "210px",
            "70px",
            "180px",
            "190px",
            "90px",
            "300px",
        ),
    )

    options = {
        request.id: (
            f"{request.public_id} · "
            f"{request.leave_type.name} · "
            f"{_status(request.status)}"
        )
        for request in requests
    }
    selected_id = st.selectbox(
        "View My Request Details",
        options=list(options),
        format_func=lambda value: options[value],
        key="employee_request_detail",
    )

    with SessionFactory() as session:
        service = LeaveService(session)
        request = service.get_request(
            current_user.company_id,
            selected_id,
        )
        plan_bytes = None

        if request and request.attachment_storage_path:
            try:
                plan_bytes = service.read_plan_file(
                    request
                )
            except FileNotFoundError:
                plan_bytes = None

    if request is None:
        return

    details = [
        {
            "Field": "Status",
            "Value": _status(request.status),
        },
        {
            "Field": "Reason",
            "Value": request.reason,
        },
        {
            "Field": "Work Handover Plan / Countermeasure",
            "Value": request.handover_plan or "Not provided",
        },
        {
            "Field": "Manager Comment",
            "Value": request.manager_comment or "—",
        },
        {
            "Field": "Posted as Used",
            "Value": (
                f"{_days(request.posted_working_days)} "
                f"of {_days(request.requested_days)} day(s)"
            ),
        },
    ]

    render_admin_table(
        details,
        key=f"employee-request-detail-{request.id}",
        min_width=850,
        column_widths=(
            "240px",
            "610px",
        ),
        compact=True,
    )

    if plan_bytes is not None:
        st.download_button(
            "Download My Handover Plan File",
            data=plan_bytes,
            file_name=(
                request.attachment_original_filename
                or "handover_plan"
            ),
            mime=(
                request.attachment_mime_type
                or "application/octet-stream"
            ),
            use_container_width=True,
            key=f"employee_plan_download_{request.id}",
        )


def _approval_rows(requests):
    """Build manager approval list rows."""

    return [
        {
            "Request ID": request.public_id,
            "Employee": (
                f"{request.employee.employee_number} · "
                f"{request.employee.full_name}"
            ),
            "Department": (
                request.employee.department.name
                if request.employee.department
                else "—"
            ),
            "Leave Type": request.leave_type.name,
            "Leave Dates": (
                f"{request.start_date.isoformat()} to "
                f"{request.end_date.isoformat()}"
            ),
            "Days": _days(request.requested_days),
            "Plan": (
                "Provided"
                if request.handover_plan
                or request.attachment_storage_path
                else "None"
            ),
            "Status": _status(request.status),
        }
        for request in requests
    ]


def _render_manager_request_detail(
    current_user: AuthenticatedUser,
    request_id: int,
) -> None:
    """Render one pending request and manager decision controls."""

    with SessionFactory() as session:
        service = LeaveService(session)
        request = service.get_request(
            current_user.company_id,
            request_id,
        )
        plan_bytes = None

        if request and request.attachment_storage_path:
            try:
                plan_bytes = service.read_plan_file(
                    request
                )
            except FileNotFoundError:
                plan_bytes = None

    if request is None:
        st.error(
            "The selected leave request is unavailable."
        )
        return

    st.markdown("### Request for Approval")

    render_admin_table(
        [
            {
                "Field": "Employee",
                "Value": (
                    f"{request.employee.employee_number} · "
                    f"{request.employee.full_name}"
                ),
            },
            {
                "Field": "Department",
                "Value": (
                    request.employee.department.name
                    if request.employee.department
                    else "—"
                ),
            },
            {
                "Field": "Leave Type",
                "Value": request.leave_type.name,
            },
            {
                "Field": "Leave Dates",
                "Value": (
                    f"{request.start_date.isoformat()} to "
                    f"{request.end_date.isoformat()}"
                ),
            },
            {
                "Field": "Working Days",
                "Value": _days(request.requested_days),
            },
            {
                "Field": "Reason",
                "Value": request.reason,
            },
            {
                "Field": "Work Handover Plan / Countermeasure",
                "Value": request.handover_plan or "Not provided",
            },
        ],
        key=f"manager-request-detail-{request.id}",
        min_width=900,
        column_widths=(
            "250px",
            "650px",
        ),
        compact=True,
    )

    if plan_bytes is not None:
        st.download_button(
            "Download Handover Plan File",
            data=plan_bytes,
            file_name=(
                request.attachment_original_filename
                or "handover_plan"
            ),
            mime=(
                request.attachment_mime_type
                or "application/octet-stream"
            ),
            use_container_width=True,
            key=f"manager_plan_download_{request.id}",
        )

    manager_comment = st.text_area(
        "Manager Comment (Optional)",
        height=110,
        max_chars=2000,
        key=f"manager_comment_{request.id}",
    )

    approve_column, reject_column = st.columns(2)

    with approve_column:
        approved = st.button(
            "Approve Leave Request",
            type="primary",
            use_container_width=True,
            key=f"approve_leave_{request.id}",
        )

    with reject_column:
        rejected = st.button(
            "Reject Leave Request",
            use_container_width=True,
            key=f"reject_leave_{request.id}",
        )

    if not approved and not rejected:
        return

    try:
        decision = LeaveDecisionInput(
            company_id=current_user.company_id,
            request_id=request.id,
            manager_employee_id=current_user.employee_id,
            manager_user_id=current_user.user_id,
            decision=(
                "approve"
                if approved
                else "reject"
            ),
            manager_comment=manager_comment,
        )

        with st.spinner(
            "Recording the manager decision…"
        ):
            with SessionFactory() as session:
                reviewed = LeaveService(
                    session
                ).decide_leave_request(decision)

        set_operation_feedback(
            (
                f"{reviewed.public_id} was "
                f"{'approved' if approved else 'rejected'}."
            ),
            namespace="leave_manager",
        )
        st.rerun()

    except (
        ValidationError,
        ValueError,
    ) as error:
        st.error(str(error))


def _render_pending_approvals(
    current_user: AuthenticatedUser,
) -> None:
    """Render requests waiting for this manager."""

    with SessionFactory() as session:
        pending = LeaveService(
            session
        ).list_pending_manager_requests(
            company_id=current_user.company_id,
            manager_employee_id=current_user.employee_id,
        )

    if not pending:
        st.success(
            "No leave request is waiting for your approval."
        )
        return

    render_admin_table(
        _approval_rows(pending),
        key="manager-pending-leave-requests",
        min_width=1250,
    )

    options = {
        request.id: (
            f"{request.public_id} · "
            f"{request.employee.full_name} · "
            f"{request.leave_type.name}"
        )
        for request in pending
    }
    selected_id = st.selectbox(
        "Select Request to Review",
        options=list(options),
        format_func=lambda value: options[value],
        key="manager_pending_selector",
    )

    _render_manager_request_detail(
        current_user,
        selected_id,
    )


def _render_reviewed_requests(
    current_user: AuthenticatedUser,
) -> None:
    """Render the current manager's reviewed request history."""

    with SessionFactory() as session:
        reviewed = LeaveService(
            session
        ).list_reviewed_manager_requests(
            company_id=current_user.company_id,
            manager_employee_id=current_user.employee_id,
        )

    if not reviewed:
        st.info(
            "You have not reviewed a leave request yet."
        )
        return

    render_admin_table(
        _approval_rows(reviewed),
        key="manager-reviewed-leave-requests",
        min_width=1250,
    )


def render_employee_leave_management_page(
    current_user: AuthenticatedUser,
) -> None:
    """Render employee requests and manager approvals in one workspace."""

    st.title("Leave Management")
    st.caption(
        "File leave, track credits, monitor request status, and review "
        "direct-report requests when you are an assigned manager."
    )
    render_operation_feedback(
        namespace="leave_employee"
    )
    render_operation_feedback(
        namespace="leave_manager"
    )

    if current_user.employee_id is None:
        st.warning(
            "Your login account is not linked to an employee record."
        )
        return

    with SessionFactory() as session:
        service = LeaveService(session)
        service.reconcile_approved_leave(
            company_id=current_user.company_id
        )
        manager_mode = service.is_manager(
            company_id=current_user.company_id,
            employee_id=current_user.employee_id,
        )

    labels = [
        "My Leave Overview",
        "File Leave Request",
        "My Requests",
    ]

    if manager_mode:
        labels.extend(
            [
                "Pending Approvals",
                "Reviewed Requests",
            ]
        )

    tabs = st.tabs(labels)

    with tabs[0]:
        _render_balances(current_user)

    with tabs[1]:
        _render_submit(current_user)

    with tabs[2]:
        _render_requests(current_user)

    if manager_mode:
        with tabs[3]:
            _render_pending_approvals(current_user)

        with tabs[4]:
            _render_reviewed_requests(current_user)
