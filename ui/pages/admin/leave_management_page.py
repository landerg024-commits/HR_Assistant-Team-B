"""Simplified administrator Leave Management workspace.

Main sections:
- Overview: operational summary and items requiring attention.
- Employee Leave Accounts: view and maintain one employee's credits.
- Leave Requests: monitor manager-routed requests and open full details.
- Leave Rules: configure company leave types and annual rules.

Department managers remain responsible for approvals outside this portal.
"""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from pydantic import ValidationError
import json
import streamlit as st
import streamlit.components.v1 as components

from authentication.current_user import AuthenticatedUser
from config.settings import get_settings
from database.session import SessionFactory
from schemas.leave_schema import (
    LeaveCreditBalanceSetInput,
    LeaveTypeInput,
)
from services.leave_service import LeaveService
from ui.components.data_table import render_admin_table
from ui.components.operation_feedback import (
    render_operation_feedback,
    set_operation_feedback,
)


_LOW_CREDIT_THRESHOLD = Decimal("2.00")


def _days(value) -> str:
    """Format leave days without unnecessary decimal zeros."""

    return (
        f"{Decimal(value):.2f}"
        .rstrip("0")
        .rstrip(".")
    )


def _format_datetime(value) -> str:
    """Display a stored datetime in the configured timezone."""

    if value is None:
        return "—"

    if value.tzinfo is None:
        value = value.replace(
            tzinfo=ZoneInfo("UTC")
        )

    return value.astimezone(
        ZoneInfo(get_settings().display_timezone)
    ).strftime("%Y-%m-%d %I:%M %p")


def _current_leave_year() -> int:
    """Return the current year in the configured timezone."""

    return datetime.now(
        ZoneInfo(get_settings().display_timezone)
    ).year


def _today():
    """Return today's date in the configured timezone."""

    return datetime.now(
        ZoneInfo(get_settings().display_timezone)
    ).date()


def _status_label(value: str) -> str:
    """Convert a stored request status into a readable label."""

    return (
        value.replace("_", " ")
        .strip()
        .title()
    )


def _group_balances(balances) -> dict[int, list]:
    """Group annual balances by employee ID."""

    grouped: dict[int, list] = {}

    for balance in balances:
        grouped.setdefault(
            balance.employee_id,
            [],
        ).append(balance)

    return grouped


def _employee_options(
    grouped: dict[int, list],
    *,
    department_name: str = "All Departments",
) -> dict[int, str]:
    """Return employee selector labels, optionally department-filtered."""

    options: dict[int, str] = {}

    for employee_id, items in grouped.items():
        employee = items[0].employee
        employee_department = (
            employee.department.name
            if employee.department
            else "No Department"
        )

        if (
            department_name != "All Departments"
            and employee_department != department_name
        ):
            continue

        options[employee_id] = (
            f"{employee.employee_number} · "
            f"{employee.full_name} · "
            f"{employee_department}"
        )

    return options


def _account_totals(balances) -> dict[str, Decimal]:
    """Calculate one employee's leave-account totals."""

    return {
        "allocated": sum(
            (
                Decimal(item.allocated_days)
                + Decimal(item.carry_over_days)
                + Decimal(item.adjustment_days)
                for item in balances
            ),
            Decimal("0.00"),
        ),
        "used": sum(
            (
                Decimal(item.used_days)
                for item in balances
            ),
            Decimal("0.00"),
        ),
        "reserved": sum(
            (
                Decimal(item.reserved_days)
                for item in balances
            ),
            Decimal("0.00"),
        ),
        "remaining": sum(
            (
                Decimal(item.remaining_days)
                for item in balances
            ),
            Decimal("0.00"),
        ),
    }


def _low_credit_rows(
    grouped: dict[int, list],
) -> list[dict[str, str]]:
    """Return one alert row per employee with low available credits."""

    rows: list[dict[str, str]] = []

    for items in grouped.values():
        employee = items[0].employee
        low_items = [
            item
            for item in items
            if (
                Decimal(item.leave_type.annual_credits) > 0
                and Decimal(item.remaining_days)
                <= _LOW_CREDIT_THRESHOLD
            )
        ]

        if not low_items:
            continue

        rows.append(
            {
                "Employee": (
                    f"{employee.employee_number} · "
                    f"{employee.full_name}"
                ),
                "Department": (
                    employee.department.name
                    if employee.department
                    else "—"
                ),
                "Low Credits": ", ".join(
                    (
                        f"{item.leave_type.name}: "
                        f"{_days(item.remaining_days)}"
                    )
                    for item in sorted(
                        low_items,
                        key=lambda value: value.leave_type.name,
                    )
                ),
            }
        )

    return rows


def _compact_request_rows(requests) -> list[dict[str, str]]:
    """Build a concise request list for the Overview tab."""

    return [
        {
            "Request ID": (
                request.public_id
                or f"LRQ_{request.id:06d}"
            ),
            "Employee": request.employee.full_name,
            "Leave Type": request.leave_type.name,
            "Leave Dates": (
                f"{request.start_date.isoformat()} to "
                f"{request.end_date.isoformat()}"
            ),
            "Days": _days(request.requested_days),
            "Credit / LWOP Split": LeaveService.allocation_breakdown(request),
            "Manager": (
                request.manager.full_name
                if request.manager
                else "—"
            ),
            "Status": _status_label(request.status),
        }
        for request in requests
    ]


def _render_overview(
    current_user: AuthenticatedUser,
    year: int,
    grouped: dict[int, list],
    requests,
) -> None:
    """Render a true dashboard without duplicating employee accounts."""

    with SessionFactory() as session:
        metrics = LeaveService(session).overview(
            current_user.company_id,
            year,
        )

    current_year = _current_leave_year()
    is_current_year = year == current_year

    metric_columns = st.columns(4)
    metric_values = [
        (
            f"Requests in {year}",
            metrics["total_requests"],
        ),
        (
            (
                "Sent This Month"
                if is_current_year
                else f"Submitted in {year}"
            ),
            (
                metrics["requests_this_month"]
                if is_current_year
                else metrics["requests_submitted_in_year"]
            ),
        ),
        (
            (
                "Employees on Leave Today"
                if is_current_year
                else f"Employees with Leave in {year}"
            ),
            (
                metrics["employees_on_leave_today"]
                if is_current_year
                else metrics["employees_with_leave"]
            ),
        ),
        (
            "Employees with Low Credits",
            metrics["employees_with_low_credits"],
        ),
    ]

    for column, (label, value) in zip(
        metric_columns,
        metric_values,
    ):
        with column:
            st.metric(label, value)

    st.info(
        "Use Overview for monitoring only. Open Employee Leave Accounts "
        "to view or adjust a specific employee's credits."
    )

    left, right = st.columns(2)

    with left:
        st.markdown(
            "### Employees on Leave Today"
            if is_current_year
            else f"### Leave Activity in {year}"
        )

        if is_current_year:
            today = _today()
            activity_requests = [
                request
                for request in requests
                if (
                    request.status in {
                        "scheduled",
                        "approved",
                        "in_progress",
                        "completed",
                    }
                    and request.start_date
                    <= today
                    <= request.end_date
                )
            ]
        else:
            activity_requests = sorted(
                requests,
                key=lambda item: (
                    item.start_date,
                    item.id,
                ),
                reverse=True,
            )[:8]

        if activity_requests:
            render_admin_table(
                _compact_request_rows(activity_requests),
                key=f"leave-overview-activity-{year}",
                min_width=920,
                compact=True,
            )
        else:
            st.info(
                "No employees are on leave today."
                if is_current_year
                else f"No leave activity is recorded for {year}."
            )

    with right:
        st.markdown("### Attention Needed")
        low_rows = _low_credit_rows(grouped)

        if low_rows:
            render_admin_table(
                low_rows,
                key=f"leave-overview-low-credit-{year}",
                min_width=680,
                column_widths=(
                    "270px",
                    "170px",
                    "240px",
                ),
                compact=True,
            )
        else:
            st.success(
                f"No employee has leave credits at or below "
                f"{_days(_LOW_CREDIT_THRESHOLD)} days for {year}."
            )

    st.markdown("### Recent Leave Requests")

    recent_requests = sorted(
        requests,
        key=lambda item: (
            item.submitted_at,
            item.id,
        ),
        reverse=True,
    )[:8]

    if recent_requests:
        render_admin_table(
            _compact_request_rows(recent_requests),
            key=f"leave-overview-recent-{year}",
            min_width=1050,
            compact=True,
        )
    else:
        st.info(
            f"No leave requests are available for {year}."
        )


def _render_employee_account_summary(
    employee,
    balances,
    year: int,
) -> None:
    """Render one employee's identity and total account metrics."""

    totals = _account_totals(balances)

    st.markdown("### Employee Leave Account")
    st.caption(
        f"{employee.employee_number} · {employee.full_name} · "
        f"{employee.department.name if employee.department else 'No Department'} "
        f"· Leave Year {year}"
    )

    columns = st.columns(4)
    cards = [
        ("Available Credits", _days(totals["remaining"])),
        ("Used Credits", _days(totals["used"])),
        ("Reserved Credits", _days(totals["reserved"])),
        ("Leave Types", len(balances)),
    ]

    for column, (label, value) in zip(
        columns,
        cards,
    ):
        with column:
            st.metric(label, value)

    with SessionFactory() as session:
        summary = LeaveService(session).entitlement_summary(
            employee=employee,
            year=year,
        )

    hire_date = (
        employee.hire_date.isoformat()
        if employee.hire_date
        else "Not recorded"
    )
    st.info(
        f"Hire Date: {hire_date} · Completed Service: "
        f"{summary['service_years']} year(s) · {summary['basis']}\n\n"
        f"Automatic Entitlement: Vacation {_days(summary['vacation_total'])} "
        f"days ({_days(summary['regular_vacation'])} regular + "
        f"{_days(summary['emergency'])} Emergency) · "
        f"Sick Leave {_days(summary['sick'])} days · LWOP 0 credits."
    )


def _render_credit_breakdown(
    employee_id: int,
    balances,
    year: int,
) -> None:
    """Display employee credits without internal adjustment arithmetic."""

    render_admin_table(
        [
            {
                "Leave Type": item.leave_type.name,
                "Annual Allocation": _days(
                    item.allocated_days
                ),
                "Carry Over": _days(
                    item.carry_over_days
                ),
                "Used": _days(item.used_days),
                "Reserved": _days(item.reserved_days),
                "Current Credits": _days(
                    item.remaining_days
                ),
                "Last Updated": _format_datetime(
                    item.updated_at
                ),
            }
            for item in sorted(
                balances,
                key=lambda value: value.leave_type.name,
            )
        ],
        key=f"employee-leave-account-{employee_id}-{year}",
        min_width=1050,
        column_widths=(
            "210px",
            "145px",
            "110px",
            "90px",
            "100px",
            "125px",
            "190px",
        ),
        max_height=360,
    )


def _render_credit_balance_editor(
    current_user: AuthenticatedUser,
    employee_id: int,
    balances,
    year: int,
) -> None:
    """Set the exact remaining credits for one selected leave type."""

    balance_by_type = {
        item.leave_type.id: item
        for item in balances
    }
    type_options = {
        leave_type_id: (
            f"{item.leave_type.name} · "
            f"{_days(item.remaining_days)} current credits"
        )
        for leave_type_id, item in balance_by_type.items()
    }

    selected_leave_type_id = st.selectbox(
        "Leave Type",
        options=list(type_options),
        format_func=lambda value: type_options[value],
        key=(
            f"leave_credit_type_"
            f"{employee_id}_{year}"
        ),
    )
    selected_balance = balance_by_type[
        selected_leave_type_id
    ]
    current_remaining = Decimal(
        selected_balance.remaining_days
    )

    st.info(
        f"Current {selected_balance.leave_type.name} credits: "
        f"{_days(current_remaining)} days. "
        "Enter the exact credits that should remain after saving."
    )

    with st.form(
        f"employee-leave-credit-set-"
        f"{employee_id}-{year}-{selected_leave_type_id}"
    ):
        new_remaining_days = st.number_input(
            "New Leave Credits",
            min_value=0.0,
            max_value=365.0,
            value=float(current_remaining),
            step=0.5,
            help=(
                "This replaces the current remaining credits. "
                "Example: current 45, enter 10, result is 10—not 55."
            ),
        )
        submitted = st.form_submit_button(
            "Save Leave Credits",
            type="primary",
            use_container_width=True,
        )

    if not submitted:
        return

    try:
        values = LeaveCreditBalanceSetInput(
            company_id=current_user.company_id,
            employee_id=employee_id,
            leave_type_id=selected_leave_type_id,
            year=year,
            new_remaining_days=Decimal(
                str(new_remaining_days)
            ),
            reason="Manual leave credit update",
            created_by_user_id=current_user.user_id,
        )

        with st.spinner("Saving leave credits…"):
            with SessionFactory() as session:
                result = LeaveService(
                    session
                ).set_credit_balance(values)

        set_operation_feedback(
            (
                f"{selected_balance.leave_type.name} credits changed "
                f"from {_days(result.previous_remaining)} to "
                f"{_days(result.new_remaining)} days."
            ),
            namespace="leave",
        )
        st.rerun()

    except (
        ValidationError,
        ValueError,
    ) as error:
        st.error(str(error))



def _credit_history_entry(item) -> str:
    """Describe either an exact balance set or a signed ledger change."""

    if item.transaction_type == "manual_balance_set":
        return f"Set to {_days(item.amount_days)} days"

    amount = Decimal(item.amount_days)
    prefix = "+" if amount > 0 else ""

    return f"{prefix}{_days(amount)} days"


def _render_credit_history(
    current_user: AuthenticatedUser,
    employee_id: int,
    year: int,
) -> None:
    """Render the immutable credit history for one employee."""

    with SessionFactory() as session:
        service = LeaveService(session)
        leave_types = {
            item.id: item.name
            for item in service.list_leave_types(
                current_user.company_id
            )
        }
        transactions = service.list_credit_history(
            current_user.company_id,
            employee_id,
            year,
        )

    if not transactions:
        st.info(
            f"No credit transactions are available for {year}."
        )
        return

    render_admin_table(
        [
            {
                "Date": _format_datetime(item.created_at),
                "Leave Type": leave_types.get(
                    item.leave_type_id,
                    "—",
                ),
                "Transaction": _status_label(
                    item.transaction_type
                ),
                "Credit Entry": _credit_history_entry(
                    item
                ),
                "Details": item.note or "—",
            }
            for item in transactions
        ],
        key=f"employee-credit-history-{employee_id}-{year}",
        min_width=900,
        column_widths=(
            "190px",
            "180px",
            "170px",
            "150px",
            "360px",
        ),
        max_height=360,
    )


def _render_employee_accounts(
    current_user: AuthenticatedUser,
    year: int,
    grouped: dict[int, list],
) -> None:
    """View and maintain all credits for one selected employee."""

    if not grouped:
        st.info(
            f"No employed employee leave accounts are available for {year}."
        )
        return

    st.info(
        "One employee account contains the complete credit view, exact "
        "credit-setting form, and transaction history."
    )

    departments = sorted(
        {
            (
                items[0].employee.department.name
                if items[0].employee.department
                else "No Department"
            )
            for items in grouped.values()
        }
    )

    filter_column, employee_column = st.columns(
        [1.1, 2.4]
    )

    with filter_column:
        selected_department = st.selectbox(
            "Department",
            options=[
                "All Departments",
                *departments,
            ],
            key=f"leave_account_department_{year}",
        )

    options = _employee_options(
        grouped,
        department_name=selected_department,
    )

    if not options:
        st.info(
            "No employee leave account matches the selected department."
        )
        return

    with employee_column:
        selected_employee_id = st.selectbox(
            "Employee",
            options=list(options),
            format_func=lambda value: options[value],
            key=f"leave_account_employee_{year}",
        )

    balances = grouped[selected_employee_id]
    employee = balances[0].employee

    _render_employee_account_summary(
        employee,
        balances,
        year,
    )
    _render_credit_breakdown(
        selected_employee_id,
        balances,
        year,
    )

    adjust_tab, history_tab = st.tabs(
        [
            "Set Leave Credits",
            "Transaction History",
        ]
    )

    with adjust_tab:
        _render_credit_balance_editor(
            current_user,
            selected_employee_id,
            balances,
            year,
        )

    with history_tab:
        _render_credit_history(
            current_user,
            selected_employee_id,
            year,
        )


def _filtered_requests(
    requests,
    *,
    department: str,
    leave_type: str,
    status: str,
    employee_search: str,
):
    """Apply the visible monitoring filters to detached request objects."""

    normalized_search = employee_search.strip().casefold()
    output = []

    for request in requests:
        request_department = (
            request.employee.department.name
            if request.employee.department
            else "No Department"
        )
        request_status = _status_label(request.status)

        if (
            department != "All Departments"
            and request_department != department
        ):
            continue

        if (
            leave_type != "All Leave Types"
            and request.leave_type.name != leave_type
        ):
            continue

        if (
            status != "All Statuses"
            and request_status != status
        ):
            continue

        if (
            normalized_search
            and normalized_search
            not in (
                f"{request.employee.employee_number} "
                f"{request.employee.full_name}"
            ).casefold()
        ):
            continue

        output.append(request)

    return output


def _render_request_details(
    current_user: AuthenticatedUser,
    selected_id: int,
) -> None:
    """Open one full request without exposing approval actions."""

    with SessionFactory() as session:
        service = LeaveService(session)
        request = service.get_request(
            current_user.company_id,
            selected_id,
        )
        cc_emails = (
            service.cc_emails(request)
            if request
            else []
        )
        attachment_bytes = None

        if request and request.attachment_storage_path:
            try:
                attachment_bytes = service.read_attachment(
                    request
                )
            except FileNotFoundError:
                attachment_bytes = None

    if request is None:
        st.error("The selected request is unavailable.")
        return

    st.markdown("### Request Details")

    render_admin_table(
        [
            {
                "Field": "Request ID",
                "Value": (
                    request.public_id
                    or f"LRQ_{request.id:06d}"
                ),
            },
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
                "Field": "Credit / LWOP Split",
                "Value": LeaveService.allocation_breakdown(request),
            },
            {
                "Field": "Manager / To",
                "Value": (
                    f"{request.manager.full_name if request.manager else '—'} "
                    f"· {request.manager_email}"
                ),
            },
            {
                "Field": "CC Recipients",
                "Value": (
                    "\n".join(cc_emails)
                    if cc_emails
                    else "—"
                ),
            },
            {
                "Field": "Status",
                "Value": _status_label(request.status),
            },
            {
                "Field": "Email Delivery",
                "Value": request.email_status.title(),
            },
            {
                "Field": "Submitted",
                "Value": _format_datetime(
                    request.submitted_at
                ),
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
        ],
        key=f"leave-request-detail-{request.id}",
        min_width=820,
        column_widths=(
            "190px",
            "630px",
        ),
        compact=True,
    )

    if attachment_bytes is not None:
        st.download_button(
            "Download Handover Plan File",
            data=attachment_bytes,
            file_name=(
                request.attachment_original_filename
                or "handover_plan"
            ),
            mime=(
                request.attachment_mime_type
                or "application/octet-stream"
            ),
            use_container_width=True,
        )

    st.caption(
        "Department managers approve or reject requests in their "
        "Employee Portal. This page is view-only."
    )


def _render_requests(
    current_user: AuthenticatedUser,
    year: int,
    requests,
    selected_request_id: int | None = None,
) -> None:
    """Render filtered, view-only manager-routed leave requests."""

    st.caption(
        f"Requests shown here have leave dates that overlap Leave Year {year}."
    )

    if not requests:
        st.info(
            f"No leave requests are available for {year}."
        )
        return

    departments = sorted(
        {
            (
                request.employee.department.name
                if request.employee.department
                else "No Department"
            )
            for request in requests
        }
    )
    leave_types = sorted(
        {
            request.leave_type.name
            for request in requests
        }
    )
    statuses = sorted(
        {
            _status_label(request.status)
            for request in requests
        }
    )

    if selected_request_id is not None:
        # A notification target must not be hidden by filters left from an
        # earlier visit to the Leave Requests tab.
        st.session_state[f"leave_request_department_{year}"] = (
            "All Departments"
        )
        st.session_state[f"leave_request_type_{year}"] = (
            "All Leave Types"
        )
        st.session_state[f"leave_request_status_{year}"] = (
            "All Statuses"
        )
        st.session_state[f"leave_request_employee_search_{year}"] = ""

    department_column, type_column, status_column = st.columns(3)

    with department_column:
        selected_department = st.selectbox(
            "Department",
            options=[
                "All Departments",
                *departments,
            ],
            key=f"leave_request_department_{year}",
        )

    with type_column:
        selected_leave_type = st.selectbox(
            "Leave Type",
            options=[
                "All Leave Types",
                *leave_types,
            ],
            key=f"leave_request_type_{year}",
        )

    with status_column:
        selected_status = st.selectbox(
            "Status",
            options=[
                "All Statuses",
                *statuses,
            ],
            key=f"leave_request_status_{year}",
        )

    employee_search = st.text_input(
        "Find Employee",
        placeholder="Employee number or name...",
        key=f"leave_request_employee_search_{year}",
    )

    filtered = _filtered_requests(
        requests,
        department=selected_department,
        leave_type=selected_leave_type,
        status=selected_status,
        employee_search=employee_search,
    )

    st.caption(
        f"{len(filtered)} of {len(requests)} request(s) shown."
    )

    if not filtered:
        st.info(
            "No leave request matches the selected filters."
        )
        return

    render_admin_table(
        [
            {
                "Request ID": (
                    request.public_id
                    or f"LRQ_{request.id:06d}"
                ),
                "Employee": request.employee.full_name,
                "Department": (
                    request.employee.department.name
                    if request.employee.department
                    else "—"
                ),
                "Leave Type": request.leave_type.name,
                "Start Date": request.start_date.isoformat(),
                "End Date": request.end_date.isoformat(),
                "Days": _days(request.requested_days),
                "Manager": (
                    request.manager.full_name
                    if request.manager
                    else "—"
                ),
                "Status": _status_label(request.status),
                "Email": request.email_status.title(),
            }
            for request in filtered
        ],
        key=f"leave-request-monitoring-{year}",
        min_width=1450,
        column_widths=(
            "125px",
            "190px",
            "155px",
            "145px",
            "110px",
            "110px",
            "75px",
            "180px",
            "145px",
            "90px",
        ),
    )

    request_options = {
        request.id: (
            f"{request.public_id or f'LRQ_{request.id:06d}'} · "
            f"{request.employee.full_name} · "
            f"{request.leave_type.name}"
        )
        for request in filtered
    }
    option_ids = list(request_options)
    selector_key = f"leave_request_detail_selector_{year}"

    if selected_request_id is not None:
        if selected_request_id not in request_options:
            st.error(
                "The notification's leave request is unavailable for "
                "the selected company and leave year."
            )
            return

        st.session_state[selector_key] = selected_request_id
        st.info(
            "Opened from Notifications. The related request is selected "
            "below inside the Leave Requests tab."
        )

    selected_id = st.selectbox(
        "View Request Details",
        options=option_ids,
        format_func=lambda value: request_options[value],
        key=selector_key,
    )

    _render_request_details(
        current_user,
        selected_id,
    )


def _render_type_form(
    current_user: AuthenticatedUser,
    leave_type,
) -> None:
    """Create or update one leave type and its annual rules."""

    form_key = (
        f"leave-type-"
        f"{'new' if leave_type is None else leave_type.id}"
    )

    with st.form(form_key):
        code = st.text_input(
            "Code *",
            value=(
                leave_type.code
                if leave_type
                else ""
            ),
            max_chars=40,
        )
        name = st.text_input(
            "Leave Type Name *",
            value=(
                leave_type.name
                if leave_type
                else ""
            ),
            max_chars=120,
        )
        annual = st.number_input(
            "Annual Credits",
            min_value=0.0,
            max_value=365.0,
            value=(
                float(leave_type.annual_credits)
                if leave_type
                else 0.0
            ),
            step=0.5,
        )
        carry = st.number_input(
            "Carry-over Limit",
            min_value=0.0,
            max_value=365.0,
            value=(
                float(leave_type.carry_over_limit)
                if leave_type
                else 0.0
            ),
            step=0.5,
        )
        notice = st.number_input(
            "Minimum Notice Days",
            min_value=0,
            max_value=365,
            value=(
                int(leave_type.minimum_notice_days)
                if leave_type
                else 0
            ),
            step=1,
        )
        paid = st.checkbox(
            "Paid Leave",
            value=(
                bool(leave_type.is_paid)
                if leave_type
                else True
            ),
        )
        requirement_options = [
            "optional",
            "recommended",
            "required",
        ]
        current_requirement = (
            leave_type.handover_plan_requirement
            if leave_type
            else "optional"
        )
        handover_plan_requirement = st.selectbox(
            "Handover Plan Requirement",
            options=requirement_options,
            index=requirement_options.index(
                current_requirement
                if current_requirement in requirement_options
                else "optional"
            ),
            format_func=lambda value: value.title(),
            help=(
                "Required accepts either plan text or an uploaded plan file. "
                "Sick and emergency leave can remain Optional."
            ),
        )
        active = st.checkbox(
            "Active",
            value=(
                bool(leave_type.is_active)
                if leave_type
                else True
            ),
        )
        apply_existing = st.checkbox(
            "Apply annual credits to existing current-year balances",
            value=False,
        )
        submitted = st.form_submit_button(
            "Save Leave Rule",
            type="primary",
            use_container_width=True,
        )

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
            requires_attachment=False,
            handover_plan_requirement=(
                handover_plan_requirement
            ),
            minimum_notice_days=int(notice),
            is_active=active,
            apply_annual_credits_to_existing=apply_existing,
        )

        with st.spinner("Saving leave rule…"):
            with SessionFactory() as session:
                LeaveService(session).save_leave_type(
                    values,
                    leave_type.id
                    if leave_type
                    else None,
                )

        set_operation_feedback(
            "Leave rule saved successfully.",
            namespace="leave",
        )
        st.rerun()

    except (
        ValidationError,
        ValueError,
    ) as error:
        st.error(str(error))


def _render_rules(
    current_user: AuthenticatedUser,
) -> None:
    """Render leave types, allocations, and request requirements."""

    st.info(
        "Automatic standard entitlement: Vacation Leave is 42 regular days "
        "+ 3 Emergency Leave days (45 total), Sick Leave is 15 days, and "
        "LWOP has zero credits. After five completed service years, Vacation "
        "and Sick Leave each gain two days. Hire-year allocations are prorated "
        "and balances reset every January."
    )

    with SessionFactory() as session:
        leave_types = LeaveService(
            session
        ).list_leave_types(
            current_user.company_id
        )

    render_admin_table(
        [
            {
                "Code": item.code,
                "Leave Type": item.name,
                "Annual Credits": _days(
                    item.annual_credits
                ),
                "Paid": (
                    "Yes" if item.is_paid else "No"
                ),
                "Carry-over Limit": _days(
                    item.carry_over_limit
                ),
                "Handover Plan": (
                    item.handover_plan_requirement
                    or "optional"
                ).title(),
                "Minimum Notice": (
                    f"{item.minimum_notice_days} day(s)"
                ),
                "Status": (
                    "Active"
                    if item.is_active
                    else "Inactive"
                ),
                "Automatic Rule": (
                    "Regular Vacation bucket; add Emergency for total entitlement; +2 after 5 years"
                    if item.code.upper() == "VACATION"
                    else "Included in Vacation total"
                    if item.code.upper() == "EMERGENCY"
                    else "+2 after 5 completed years"
                    if item.code.upper() == "SICK"
                    else "Automatic excess when paid credits are insufficient"
                    if item.code.upper() == "LWOP"
                    else "Uses configured annual credits"
                ),
            }
            for item in leave_types
        ],
        key="leave-rules-table",
        min_width=1500,
        max_height=360,
    )

    add_tab, edit_tab = st.tabs(
        [
            "Add Leave Rule",
            "Edit Leave Rule",
        ]
    )

    with add_tab:
        _render_type_form(
            current_user,
            None,
        )

    with edit_tab:
        if not leave_types:
            st.info("No leave rule is available to edit.")
            return

        options = {
            item.id: f"{item.code} · {item.name}"
            for item in leave_types
        }
        selected_id = st.selectbox(
            "Select Leave Rule",
            options=list(options),
            format_func=lambda value: options[value],
        )
        selected = next(
            item
            for item in leave_types
            if item.id == selected_id
        )
        _render_type_form(
            current_user,
            selected,
        )


def _notification_leave_request_id() -> int | None:
    """Return a safe request ID opened from a notification."""

    raw_value = st.query_params.get("leave_request_id")
    if isinstance(raw_value, (list, tuple)):
        raw_value = raw_value[0] if raw_value else None

    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return None

    return value if value > 0 else None


def _activate_leave_tab(tab_label: str) -> None:
    """Select one visible Streamlit tab after notification navigation."""

    target_label_json = json.dumps(tab_label)
    script = (
        "<script>"
        "const parentDocument=window.parent.document;"
        f"const targetLabel={target_label_json};"
        "const activateTargetTab=()=>{"
        "const tabs=Array.from(parentDocument.querySelectorAll("
        "'[data-testid=\"stTabs\"] button[role=\"tab\"]'));"
        "const target=tabs.find((tab)=>tab.textContent.trim()===targetLabel);"
        "if(target&&target.getAttribute('aria-selected')!=='true'){target.click();}"
        "};"
        "activateTargetTab();"
        "window.setTimeout(activateTargetTab,80);"
        "window.setTimeout(activateTargetTab,220);"
        "</script>"
    )
    components.html(script, height=0, width=0)


def _notification_request_year(
    current_user: AuthenticatedUser,
    request_id: int | None,
) -> int | None:
    """Return the target request year after company-scoped validation."""

    if request_id is None:
        return None

    with SessionFactory() as session:
        request = LeaveService(session).get_request(
            current_user.company_id,
            request_id,
        )

    if request is None:
        return None

    return request.start_date.year


def render_admin_leave_management_page(
    current_user: AuthenticatedUser,
) -> None:
    """Render the simplified company-scoped Leave Management page."""

    st.title("Leave Management")
    st.caption(
        "Monitor leave activity, maintain employee leave accounts, "
        "review manager-routed requests, and configure leave rules."
    )
    render_operation_feedback(
        namespace="leave"
    )

    notification_request_id = _notification_leave_request_id()
    notification_year = _notification_request_year(
        current_user,
        notification_request_id,
    )

    if notification_request_id is not None and notification_year is None:
        st.error(
            "The leave request linked to this notification is unavailable."
        )

    if notification_year is not None:
        st.session_state["leave_management_year"] = notification_year

    selected_year = int(
        st.number_input(
            "Leave Year",
            min_value=2000,
            max_value=2200,
            value=(
                notification_year
                if notification_year is not None
                else _current_leave_year()
            ),
            step=1,
            key="leave_management_year",
            help=(
                "The selected year applies to Overview, Employee Leave "
                "Accounts, and Leave Requests."
            ),
        )
    )

    with SessionFactory() as session:
        service = LeaveService(session)
        balances = service.list_company_balances(
            current_user.company_id,
            selected_year,
        )
        requests = service.list_company_requests(
            current_user.company_id,
            selected_year,
        )

    grouped = _group_balances(balances)

    overview_tab, accounts_tab, requests_tab, rules_tab = st.tabs(
        [
            "Overview",
            "Employee Leave Accounts",
            "Leave Requests",
            "Leave Rules",
        ]
    )

    with overview_tab:
        _render_overview(
            current_user,
            selected_year,
            grouped,
            requests,
        )

    with accounts_tab:
        _render_employee_accounts(
            current_user,
            selected_year,
            grouped,
        )

    with requests_tab:
        _render_requests(
            current_user,
            selected_year,
            requests,
            selected_request_id=notification_request_id,
        )

    with rules_tab:
        _render_rules(current_user)

    if notification_request_id is not None:
        _activate_leave_tab("Leave Requests")
