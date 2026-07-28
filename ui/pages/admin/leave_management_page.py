"""Administrator leave monitoring, credits, and rule configuration."""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from pydantic import ValidationError
import streamlit as st

from authentication.current_user import AuthenticatedUser
from config.settings import get_settings
from database.session import SessionFactory
from schemas.leave_schema import LeaveCreditAdjustmentInput, LeaveTypeInput
from services.leave_service import LeaveService
from ui.components.data_table import render_admin_table
from ui.components.operation_feedback import render_operation_feedback, set_operation_feedback


def _days(value) -> str:
    return f"{Decimal(value):.2f}".rstrip("0").rstrip(".")


def _format_datetime(value) -> str:
    if value is None:
        return "—"
    settings = get_settings()
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(ZoneInfo(settings.display_timezone)).strftime("%Y-%m-%d %I:%M %p")


def _render_overview(current_user: AuthenticatedUser) -> None:
    with SessionFactory() as session:
        metrics = LeaveService(session).overview(current_user.company_id)
    columns = st.columns(4)
    labels = (
        ("Total Leave Requests", metrics["total_requests"]),
        ("Requests Sent This Month", metrics["requests_this_month"]),
        ("Employees on Leave Today", metrics["employees_on_leave_today"]),
        ("Employees with Low Credits", metrics["employees_with_low_credits"]),
    )
    for column, (label, value) in zip(columns, labels):
        with column:
            st.metric(label, value)
    st.info(
        "Department managers handle approval through the emailed request. "
        "HR/Admin uses this module for monitoring, leave credits, and rules only."
    )


def _render_credits(current_user: AuthenticatedUser) -> None:
    year = st.number_input("Leave Year", min_value=2000, max_value=2200, value=datetime.now().year, step=1)
    with SessionFactory() as session:
        service = LeaveService(session)
        balances = service.list_company_balances(current_user.company_id, int(year))

    grouped: dict[int, list] = {}
    for balance in balances:
        grouped.setdefault(balance.employee_id, []).append(balance)

    rows = []
    for employee_balances in grouped.values():
        employee = employee_balances[0].employee
        by_name = {item.leave_type.name.lower(): item for item in employee_balances}
        vacation = by_name.get("vacation leave")
        sick = by_name.get("sick leave")
        other_remaining = sum(
            (Decimal(item.remaining_days) for item in employee_balances if item.leave_type.name.lower() not in {"vacation leave", "sick leave"}),
            Decimal("0.00"),
        )
        rows.append({
            "Employee Number": employee.employee_number,
            "Employee Name": employee.full_name,
            "Department": employee.department.name if employee.department else "—",
            "Vacation Leave": _days(vacation.remaining_days) if vacation else "0",
            "Sick Leave": _days(sick.remaining_days) if sick else "0",
            "Other Leave": _days(other_remaining),
            "Used": _days(sum((Decimal(item.used_days) for item in employee_balances), Decimal("0.00"))),
            "Reserved": _days(sum((Decimal(item.reserved_days) for item in employee_balances), Decimal("0.00"))),
            "Remaining": _days(sum((Decimal(item.remaining_days) for item in employee_balances), Decimal("0.00"))),
            "Last Updated": _format_datetime(max(item.updated_at for item in employee_balances)),
        })
    if rows:
        render_admin_table(rows, key=f"leave-credits-{year}", min_width=1500, column_widths=("135px", "200px", "160px", "120px", "110px", "110px", "85px", "90px", "100px", "190px"))
    else:
        st.info("No employed employee records are available.")
        return

    employee_options = {items[0].employee.id: f"{items[0].employee.employee_number} · {items[0].employee.full_name}" for items in grouped.values()}
    selected_employee_id = st.selectbox(
        "View employee credit details",
        options=list(employee_options),
        format_func=lambda value: employee_options[value],
    )
    selected_balances = grouped[selected_employee_id]
    details, adjust, history = st.tabs(["Credit Details", "Adjust Credits", "Credit History"])
    with details:
        render_admin_table([
            {
                "Leave Type": item.leave_type.name,
                "Allocated": _days(item.allocated_days),
                "Carry Over": _days(item.carry_over_days),
                "Adjustments": _days(item.adjustment_days),
                "Used": _days(item.used_days),
                "Reserved": _days(item.reserved_days),
                "Remaining": _days(item.remaining_days),
            }
            for item in selected_balances
        ], key=f"credit-details-{selected_employee_id}-{year}", min_width=850)
    with adjust:
        type_options = {item.leave_type.id: item.leave_type.name for item in selected_balances}
        with st.form(f"leave-credit-adjust-{selected_employee_id}-{year}"):
            leave_type_id = st.selectbox("Leave Type", options=list(type_options), format_func=lambda value: type_options[value])
            amount = st.number_input("Adjustment Days", min_value=-365.0, max_value=365.0, step=0.5, help="Use a positive value to add credits or a negative value to subtract credits.")
            reason = st.text_input("Reason *", max_chars=500)
            submitted = st.form_submit_button("Apply Credit Adjustment", type="primary", use_container_width=True)
        if submitted:
            try:
                request = LeaveCreditAdjustmentInput(
                    company_id=current_user.company_id,
                    employee_id=selected_employee_id,
                    leave_type_id=leave_type_id,
                    year=int(year),
                    adjustment_days=Decimal(str(amount)),
                    reason=reason,
                    created_by_user_id=current_user.user_id,
                )
                with st.spinner("Updating leave credits…"):
                    with SessionFactory() as session:
                        LeaveService(session).adjust_credit(request)
                set_operation_feedback("Leave credits updated successfully.", namespace="leave")
                st.rerun()
            except (ValidationError, ValueError) as error:
                st.error(str(error))
    with history:
        with SessionFactory() as session:
            service = LeaveService(session)
            types = {item.id: item.name for item in service.list_leave_types(current_user.company_id)}
            transactions = service.list_credit_history(current_user.company_id, selected_employee_id, int(year))
        if transactions:
            render_admin_table([
                {
                    "Date": _format_datetime(item.created_at),
                    "Leave Type": types.get(item.leave_type_id, "—"),
                    "Transaction": item.transaction_type.replace("_", " ").title(),
                    "Days": _days(item.amount_days),
                    "Note": item.note or "—",
                }
                for item in transactions
            ], key=f"credit-history-{selected_employee_id}-{year}", min_width=900)
        else:
            st.info("No credit history is available.")


def _render_requests(current_user: AuthenticatedUser) -> None:
    with SessionFactory() as session:
        requests = LeaveService(session).list_company_requests(current_user.company_id)
    if not requests:
        st.info("No leave requests have been submitted.")
        return
    render_admin_table([
        {
            "Request ID": request.public_id or f"LRQ_{request.id:06d}",
            "Employee": request.employee.full_name,
            "Department": request.employee.department.name if request.employee.department else "—",
            "Leave Type": request.leave_type.name,
            "Start Date": request.start_date.isoformat(),
            "End Date": request.end_date.isoformat(),
            "Days": _days(request.requested_days),
            "Manager": request.manager.full_name if request.manager else "—",
            "Date Submitted": _format_datetime(request.submitted_at),
            "Status": request.status.replace("_", " ").title(),
            "Email": request.email_status.title(),
        }
        for request in requests
    ], key="leave-request-monitoring", min_width=1600, column_widths=("125px", "190px", "145px", "145px", "110px", "110px", "70px", "180px", "185px", "145px", "90px"))
    options = {request.id: f"{request.public_id} · {request.employee.full_name} · {request.leave_type.name}" for request in requests}
    selected_id = st.selectbox("View Request Details", options=list(options), format_func=lambda value: options[value])
    with SessionFactory() as session:
        service = LeaveService(session)
        request = service.get_request(current_user.company_id, selected_id)
        cc_emails = service.cc_emails(request)
        attachment_bytes = None
        if request and request.attachment_storage_path:
            try:
                attachment_bytes = service.read_attachment(request)
            except FileNotFoundError:
                attachment_bytes = None
    if request is None:
        st.error("The selected request is unavailable.")
        return
    st.markdown("### Request Details")
    render_admin_table([
        {"Field": "Request ID", "Value": request.public_id},
        {"Field": "Employee", "Value": f"{request.employee.employee_number} · {request.employee.full_name}"},
        {"Field": "Department", "Value": request.employee.department.name if request.employee.department else "—"},
        {"Field": "Leave Type", "Value": request.leave_type.name},
        {"Field": "Dates", "Value": f"{request.start_date.isoformat()} to {request.end_date.isoformat()}"},
        {"Field": "Working Days", "Value": _days(request.requested_days)},
        {"Field": "Manager / To", "Value": f"{request.manager.full_name if request.manager else '—'} · {request.manager_email}"},
        {"Field": "CC Recipients", "Value": "\n".join(cc_emails) if cc_emails else "—"},
        {"Field": "Status", "Value": request.status.replace("_", " ").title()},
        {"Field": "Email Delivery", "Value": request.email_status.title()},
        {"Field": "Reason", "Value": request.reason},
    ], key=f"leave-request-detail-{request.id}", min_width=800, column_widths=("190px", "610px"), compact=True)
    if attachment_bytes is not None:
        st.download_button(
            "Download Supporting Attachment",
            data=attachment_bytes,
            file_name=request.attachment_original_filename or "leave_attachment",
            mime=request.attachment_mime_type or "application/octet-stream",
            use_container_width=True,
        )
    st.caption("Approval, rejection, and cancellation are handled by the department manager outside the HR Admin portal.")


def _render_types(current_user: AuthenticatedUser) -> None:
    with SessionFactory() as session:
        types = LeaveService(session).list_leave_types(current_user.company_id)
    render_admin_table([
        {
            "Code": item.code,
            "Leave Type": item.name,
            "Annual Credits": _days(item.annual_credits),
            "Paid": "Yes" if item.is_paid else "No",
            "Carry-over Limit": _days(item.carry_over_limit),
            "Requires Attachment": "Yes" if item.requires_attachment else "No",
            "Minimum Notice": f"{item.minimum_notice_days} day(s)",
            "Status": "Active" if item.is_active else "Inactive",
        }
        for item in types
    ], key="leave-type-rules", min_width=1200)
    add_tab, edit_tab = st.tabs(["Add Leave Type", "Edit Leave Type"])
    with add_tab:
        _render_type_form(current_user, None)
    with edit_tab:
        options = {item.id: f"{item.code} · {item.name}" for item in types}
        selected_id = st.selectbox("Select Leave Type", options=list(options), format_func=lambda value: options[value])
        selected = next(item for item in types if item.id == selected_id)
        _render_type_form(current_user, selected)


def _render_type_form(current_user: AuthenticatedUser, leave_type) -> None:
    form_key = f"leave-type-{'new' if leave_type is None else leave_type.id}"
    with st.form(form_key):
        code = st.text_input("Code *", value=leave_type.code if leave_type else "", max_chars=40)
        name = st.text_input("Leave Type Name *", value=leave_type.name if leave_type else "", max_chars=120)
        annual = st.number_input("Annual Credits", min_value=0.0, max_value=365.0, value=float(leave_type.annual_credits) if leave_type else 0.0, step=0.5)
        carry = st.number_input("Carry-over Limit", min_value=0.0, max_value=365.0, value=float(leave_type.carry_over_limit) if leave_type else 0.0, step=0.5)
        notice = st.number_input("Minimum Notice Days", min_value=0, max_value=365, value=int(leave_type.minimum_notice_days) if leave_type else 0, step=1)
        paid = st.checkbox("Paid Leave", value=bool(leave_type.is_paid) if leave_type else True)
        requires_attachment = st.checkbox("Requires Attachment", value=bool(leave_type.requires_attachment) if leave_type else False)
        active = st.checkbox("Active", value=bool(leave_type.is_active) if leave_type else True)
        apply_existing = st.checkbox("Apply annual credits to existing current-year balances", value=False)
        submitted = st.form_submit_button("Save Leave Type", type="primary", use_container_width=True)
    if not submitted:
        return
    try:
        values = LeaveTypeInput(
            company_id=current_user.company_id,
            code=code,
            name=name,
            annual_credits=Decimal(str(annual)),
            is_paid=paid,
            carry_over_limit=Decimal(str(carry)),
            requires_attachment=requires_attachment,
            minimum_notice_days=int(notice),
            is_active=active,
            apply_annual_credits_to_existing=apply_existing,
        )
        with st.spinner("Saving leave type and rules…"):
            with SessionFactory() as session:
                LeaveService(session).save_leave_type(values, leave_type.id if leave_type else None)
        set_operation_feedback("Leave type settings saved.", namespace="leave")
        st.rerun()
    except (ValidationError, ValueError) as error:
        st.error(str(error))


def render_admin_leave_management_page(current_user: AuthenticatedUser) -> None:
    """Render HR monitoring without approval/rejection controls."""

    st.title("Leave Management")
    st.caption("View employee credits, monitor manager-routed requests, and configure leave rules.")
    render_operation_feedback(namespace="leave")
    overview, credits, requests, settings = st.tabs(["Leave Overview", "Leave Credits", "Leave Requests", "Leave Types & Rules"])
    with overview:
        _render_overview(current_user)
    with credits:
        _render_credits(current_user)
    with requests:
        _render_requests(current_user)
    with settings:
        _render_types(current_user)
