"""Employee leave credits, request submission, and request history."""

from datetime import date, timedelta
from decimal import Decimal

from pydantic import ValidationError
import streamlit as st

from authentication.current_user import AuthenticatedUser
from config.settings import get_settings
from database.session import SessionFactory
from schemas.leave_schema import LeaveRequestInput
from services.leave_service import LeaveService
from ui.components.data_table import render_admin_table
from ui.components.operation_feedback import render_operation_feedback, set_operation_feedback


_LEAVE_FORM_NONCE_KEY = "_employee_leave_form_nonce"


def _days(value) -> str:
    return f"{Decimal(value):.2f}".rstrip("0").rstrip(".")


def _nonce() -> int:
    value = int(st.session_state.get(_LEAVE_FORM_NONCE_KEY, 0))
    st.session_state[_LEAVE_FORM_NONCE_KEY] = value
    return value


def _key(nonce: int, name: str) -> str:
    return f"employee_leave_{nonce}_{name}"


def _render_balances(current_user: AuthenticatedUser) -> None:
    if current_user.employee_id is None:
        st.warning("Your login account is not linked to an employee record.")
        return
    with SessionFactory() as session:
        balances = LeaveService(session).list_employee_balances(current_user.company_id, current_user.employee_id)
    if not balances:
        st.info("No leave credits are configured.")
        return
    columns = st.columns(min(4, len(balances)))
    for column, balance in zip(columns, balances[:4]):
        with column:
            st.metric(balance.leave_type.name, _days(balance.remaining_days), delta=f"{_days(balance.reserved_days)} reserved" if balance.reserved_days else None)
    render_admin_table([
        {
            "Leave Type": balance.leave_type.name,
            "Allocated": _days(balance.allocated_days),
            "Carry Over": _days(balance.carry_over_days),
            "Adjustments": _days(balance.adjustment_days),
            "Used": _days(balance.used_days),
            "Reserved": _days(balance.reserved_days),
            "Remaining": _days(balance.remaining_days),
        }
        for balance in balances
    ], key="employee-leave-balances", min_width=850)


def _render_submit(current_user: AuthenticatedUser) -> None:
    if current_user.employee_id is None:
        st.warning("Your login account is not linked to an employee record.")
        return
    settings = get_settings()
    nonce = _nonce()
    with SessionFactory() as session:
        service = LeaveService(session)
        balances = service.list_employee_balances(current_user.company_id, current_user.employee_id)
        employee = service.employee_repository.get_with_details(company_id=current_user.company_id, employee_id=current_user.employee_id)
        admin_emails = service._admin_cc_emails(current_user.company_id, exclude=set())
    if employee is None:
        st.error("Your employee record is unavailable.")
        return
    manager_email = LeaveService._email_for_employee(employee.manager)
    st.info(
        f"Request recipient: {employee.manager.full_name if employee.manager else 'No manager assigned'}"
        f"{f' · {manager_email}' if manager_email else ''}. "
        "Your registered email and active company administrators are copied on the request."
    )
    if admin_emails:
        st.caption("Automatic CC: " + ", ".join(admin_emails))
    type_options = {balance.leave_type_id: balance for balance in balances if balance.leave_type.is_active}
    with st.form(_key(nonce, "form")):
        leave_type_id = st.selectbox(
            "Leave Type *",
            options=list(type_options),
            format_func=lambda value: f"{type_options[value].leave_type.name} · {_days(type_options[value].remaining_days)} available",
            key=_key(nonce, "type"),
        )
        start = st.date_input("Start Date *", value=date.today(), key=_key(nonce, "start"))
        end = st.date_input("End Date *", value=date.today(), key=_key(nonce, "end"))
        reason = st.text_area("Reason *", height=150, max_chars=4000, key=_key(nonce, "reason"))
        attachment = st.file_uploader(
            "Supporting Attachment",
            type=["pdf", "docx", "png", "jpg", "jpeg"],
            help=f"Maximum {settings.leave_attachment_max_mb} MB. Required only when the selected leave rule requires it.",
            key=_key(nonce, "attachment"),
        )
        submitted = st.form_submit_button("Send Leave Request to Manager", type="primary", use_container_width=True)
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
        )
        with st.spinner("Recording request and emailing your manager…"):
            with SessionFactory() as session:
                result = LeaveService(session).submit_leave_request(
                    values,
                    attachment_filename=attachment.name if attachment else None,
                    attachment_bytes=attachment.getvalue() if attachment else None,
                    attachment_mime_type=attachment.type if attachment else None,
                )
        st.session_state[_LEAVE_FORM_NONCE_KEY] = nonce + 1
        set_operation_feedback(
            result.message,
            namespace="leave_employee",
            level="success" if result.email_sent else "warning",
        )
        st.rerun()
    except (ValidationError, ValueError) as error:
        st.error(str(error))
    except Exception:
        st.error("The leave request could not be processed.")


def _render_requests(current_user: AuthenticatedUser) -> None:
    if current_user.employee_id is None:
        st.warning("Your login account is not linked to an employee record.")
        return
    with SessionFactory() as session:
        requests = LeaveService(session).list_employee_requests(current_user.company_id, current_user.employee_id)
    if not requests:
        st.info("You have not submitted a leave request yet.")
        return
    render_admin_table([
        {
            "Request ID": request.public_id,
            "Leave Type": request.leave_type.name,
            "Start Date": request.start_date.isoformat(),
            "End Date": request.end_date.isoformat(),
            "Days": _days(request.requested_days),
            "Manager": request.manager.full_name if request.manager else "—",
            "Status": request.status.replace("_", " ").title(),
            "Email": request.email_status.title(),
            "Reason": request.reason,
        }
        for request in requests
    ], key="employee-leave-requests", min_width=1250)


def render_employee_leave_management_page(current_user: AuthenticatedUser) -> None:
    """Render employee leave credits, request form, and history."""

    st.title("Leave Management")
    st.caption("Review your credits and send leave requests directly to your assigned manager.")
    render_operation_feedback(namespace="leave_employee")
    credits, submit, history = st.tabs(["My Leave Credits", "Submit Leave Request", "My Requests"])
    with credits:
        _render_balances(current_user)
    with submit:
        _render_submit(current_user)
    with history:
        _render_requests(current_user)
