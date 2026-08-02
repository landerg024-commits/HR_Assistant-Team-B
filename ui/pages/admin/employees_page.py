"""Editable Employee Master Record administration page.

The page intentionally combines employee profile, training checklist, and
login-account information. Roles are no longer administered separately.
"""

from datetime import date
from html import escape
import re

import streamlit as st
from pydantic import ValidationError

from authentication.current_user import AuthenticatedUser
from core.constants import CLEARANCE_LABELS
from database.session import SessionFactory
from schemas.admin_management_schema import (
    EmployeeAccountCreate,
    EmployeeDeleteRequest,
    EmployeeMasterUpdate,
    TrainingItemInput,
)
from services.admin_management_service import (
    AdminManagementService,
)
from ui.components.operation_feedback import (
    render_operation_feedback,
    set_operation_feedback,
)


EMPLOYMENT_STATUS_OPTIONS = {
    "Employed — Account Active": "employed",
    "Resigned — Account Inactive": "resigned",
}


def _parse_training_text(
    value: str,
) -> list[TrainingItemInput]:
    """Parse one checklist item per line.

    Accepted examples:
    [x] Safety Orientation
    [ ] Data Privacy
    Orientation
    """

    items: list[TrainingItemInput] = []

    for raw_line in value.splitlines():
        line = raw_line.strip()

        if not line:
            continue

        completed = False

        completed_match = re.match(
            r"^\[(x|X|✓)\]\s*(.+)$",
            line,
        )
        pending_match = re.match(
            r"^\[\s\]\s*(.+)$",
            line,
        )

        if completed_match:
            completed = True
            title = completed_match.group(2).strip()
        elif pending_match:
            title = pending_match.group(1).strip()
        else:
            title = line.lstrip("•-").strip()

        if title:
            items.append(
                TrainingItemInput(
                    title=title,
                    is_completed=completed,
                )
            )

    return items


def _training_editor_value(employee) -> str:
    """Convert stored training rows into editable checklist text."""

    return "\n".join(
        (
            "[x] "
            if item.is_completed
            else "[ ] "
        )
        + item.title
        for item in employee.trainings
    )


def _training_cell(employee) -> str:
    """Combine training rows into one table cell."""

    if not employee.trainings:
        return "—"

    return "\n".join(
        (
            "☑ "
            if item.is_completed
            else "☐ "
        )
        + item.title
        for item in employee.trainings
    )


def _account_cell(employee) -> str:
    """Build one compact account summary cell."""

    if employee.user is None:
        return "No account"

    clearance_label = CLEARANCE_LABELS.get(
        employee.user.clearance,
        "Unknown",
    )

    account_status = (
        "Active"
        if employee.user.is_active
        else "Inactive"
    )

    return (
        f"ID: {employee.user.id}\n"
        f"Username: {employee.user.username}\n"
        f"Clearance: {employee.user.clearance} - "
        f"{clearance_label}\n"
        f"Account: {account_status}"
    )


def _employee_rows(
    employees,
) -> list[dict[str, object]]:
    """Build a compact employee-list summary without duplicate name fields."""

    return [
        {
            "Employee Number": employee.employee_number,
            "Full Name": employee.full_name,
            "Job Title / Position": employee.job_title or "—",
            "Department": (
                employee.department.name
                if employee.department
                else "—"
            ),
            "Manager": (
                employee.manager.full_name
                if employee.manager
                else "—"
            ),
            "Email / Telephone / Mobile No.": (
                f"Email: {employee.work_email or '—'}\n"
                f"Tel/Mobile: {employee.telephone_mobile_no or '—'}"
            ),
            "Status": (
                "Employed\nAccount Active"
                if employee.employment_status == "employed"
                else "Resigned\nAccount Inactive"
            ),
            "Training": _training_cell(employee),
            "Account": _account_cell(employee),
        }
        for employee in employees
    ]


def _employee_search_value(employee) -> str:
    """Build one normalized searchable value for an employee record."""

    values = [
        employee.employee_number,
        employee.full_name,
        employee.first_name,
        employee.middle_name,
        employee.last_name,
        employee.suffix,
        employee.work_email,
        employee.telephone_mobile_no,
        employee.job_title,
        employee.employment_status,
        (
            employee.department.name
            if employee.department
            else ""
        ),
        (
            employee.manager.full_name
            if employee.manager
            else ""
        ),
        (
            employee.user.username
            if employee.user
            else ""
        ),
        (
            "active"
            if employee.user and employee.user.is_active
            else "inactive"
        ),
        *(
            item.title
            for item in employee.trainings
        ),
    ]

    return " ".join(
        str(value).strip().casefold()
        for value in values
        if value not in (None, "")
    )


def _filter_employees(
    employees,
    search_text: str,
):
    """Filter by employee, account, department, manager, or training text."""

    normalized = search_text.strip().casefold()

    if not normalized:
        return list(employees)

    return [
        employee
        for employee in employees
        if normalized in _employee_search_value(employee)
    ]


def _manager_options(
    employees,
    *,
    exclude_employee_id: int | None = None,
) -> dict[str, int | None]:
    """Return readable manager choices excluding the edited employee."""

    return {
        "No Manager": None,
        **{
            (
                f"{employee.employee_number} — "
                f"{employee.full_name}"
            ): employee.id
            for employee in employees
            if (
                exclude_employee_id is None
                or employee.id != exclude_employee_id
            )
            and employee.employment_status == "employed"
        },
    }


def _validation_message(
    error: ValidationError,
) -> str:
    """Return one readable Pydantic validation message."""

    first = error.errors()[0]
    message = str(
        first.get("msg", "The submitted value is invalid.")
    )

    return message.removeprefix("Value error, ")


def _html_cell(value: object) -> str:
    """Escape one table value and preserve its line breaks safely."""

    if value is None:
        return ""

    escaped = escape(str(value))

    return escaped.replace("\n", "<br>")


def _render_wrapped_employee_table(
    rows: list[dict[str, object]],
) -> None:
    """Render all matching employees in a five-record scroll viewport."""

    headers = list(rows[0].keys())

    header_html = "".join(
        f"<th>{escape(header)}</th>"
        for header in headers
    )

    body_rows: list[str] = []

    for row in rows:
        cells = "".join(
            (
                "<td><div class=\"employee-table-cell\">"
                f"{_html_cell(row.get(header, ''))}"
                "</div></td>"
            )
            for header in headers
        )

        body_rows.append(
            f"<tr>{cells}</tr>"
        )

    table_html = f"""
    <style>
        .employee-table-shell {{
            width: 100%;
            height: auto;
            max-height: 432px;
            overflow-x: scroll;
            overflow-y: scroll;
            scrollbar-gutter: stable both-edges;
            scrollbar-width: auto;
            scrollbar-color: var(--hr-primary) var(--hr-border);
            border: 1px solid var(--hr-border);
            border-radius: 14px;
            background: var(--hr-surface);
        }}

        .employee-table-shell::-webkit-scrollbar {{
            width: 13px;
            height: 13px;
        }}

        .employee-table-shell::-webkit-scrollbar-track {{
            background: var(--hr-background);
            border: 1px solid var(--hr-border);
            border-radius: 10px;
        }}

        .employee-table-shell::-webkit-scrollbar-thumb {{
            min-height: 36px;
            background: var(--hr-primary);
            border: 2px solid var(--hr-background);
            border-radius: 10px;
        }}

        .employee-table-shell::-webkit-scrollbar-corner {{
            background: var(--hr-background);
        }}

        .employee-master-table {{
            width: 100%;
            min-width: 1320px;
            border-collapse: separate;
            border-spacing: 0;
            table-layout: fixed;
            font-size: 0.84rem;
        }}

        .employee-master-table th {{
            position: sticky;
            top: 0;
            z-index: 2;
            height: 46px;
            padding: 8px 10px;
            border-right: 1px solid var(--hr-border);
            border-bottom: 1px solid var(--hr-border);
            background: var(--hr-surface);
            color: var(--hr-text-primary);
            text-align: left;
            vertical-align: middle;
            white-space: normal;
            overflow-wrap: anywhere;
            word-break: break-word;
            line-height: 1.3;
        }}

        .employee-master-table tbody tr {{
            height: 72px;
        }}

        .employee-master-table td {{
            height: 72px;
            padding: 8px 10px;
            border-right: 1px solid var(--hr-border);
            border-bottom: 1px solid var(--hr-border);
            color: var(--hr-text-secondary);
            text-align: left;
            vertical-align: top;
            white-space: normal;
            overflow-wrap: anywhere;
            word-break: break-word;
            line-height: 1.4;
            transition:
                color 0.14s ease,
                background-color 0.14s ease;
        }}

        .employee-table-cell {{
            max-height: 56px;
            overflow: hidden;
        }}

        .employee-master-table th:last-child,
        .employee-master-table td:last-child {{
            border-right: 0;
        }}

        .employee-master-table tbody tr:hover td {{
            color: var(--hr-text-primary);
            background: var(--hr-primary-soft);
        }}

        .employee-master-table th:nth-child(1),
        .employee-master-table td:nth-child(1) {{
            width: 120px;
            position: sticky;
            left: 0;
            z-index: 3;
            background: var(--hr-surface);
        }}

        .employee-master-table th:nth-child(2),
        .employee-master-table td:nth-child(2) {{
            width: 175px;
            position: sticky;
            left: 120px;
            z-index: 3;
            background: var(--hr-surface);
            box-shadow: 8px 0 12px rgba(15, 23, 42, 0.04);
        }}

        .employee-master-table th:nth-child(1),
        .employee-master-table th:nth-child(2) {{
            z-index: 5;
        }}

        .employee-master-table tbody tr:hover td:nth-child(1),
        .employee-master-table tbody tr:hover td:nth-child(2) {{
            background: var(--hr-primary-soft);
        }}

        .employee-master-table th:nth-child(3),
        .employee-master-table td:nth-child(3) {{
            width: 155px;
        }}

        .employee-master-table th:nth-child(4),
        .employee-master-table td:nth-child(4) {{
            width: 135px;
        }}

        .employee-master-table th:nth-child(5),
        .employee-master-table td:nth-child(5) {{
            width: 155px;
        }}

        .employee-master-table th:nth-child(6),
        .employee-master-table td:nth-child(6) {{
            width: 225px;
        }}

        .employee-master-table th:nth-child(7),
        .employee-master-table td:nth-child(7) {{
            width: 130px;
        }}

        .employee-master-table th:nth-child(8),
        .employee-master-table td:nth-child(8) {{
            width: 210px;
        }}

        .employee-master-table th:nth-child(9),
        .employee-master-table td:nth-child(9) {{
            width: 215px;
        }}
    </style>

    <div class="employee-table-shell" role="region"
         aria-label="Scrollable employee list" tabindex="0">
        <table class="employee-master-table">
            <thead>
                <tr>{header_html}</tr>
            </thead>
            <tbody>
                {''.join(body_rows)}
            </tbody>
        </table>
    </div>
    """

    st.markdown(
        table_html,
        unsafe_allow_html=True,
    )


def _render_employee_list(employees) -> None:
    """Display a searchable list with five records visible at a time."""

    st.subheader("Employee List")
    st.caption(
        "Search any employee, account, department, manager, or training. "
        "Five records are visible; scroll for more rows. Detailed name "
        "fields remain available in Add/Edit Employee."
    )

    search_text = st.text_input(
        "Search Employees",
        placeholder=(
            "Search employee number, name, email, telephone/mobile, "
            "department, manager, position, username, or training..."
        ),
        key="employee_master_search",
    )

    filtered = _filter_employees(
        employees,
        search_text,
    )
    rows = _employee_rows(filtered)

    st.caption(
        f"Showing {len(filtered)} of {len(employees)} employee record(s)."
    )

    if not rows:
        st.info(
            "No employee record matches the current search."
        )
        return

    _render_wrapped_employee_table(rows)


def _render_add_employee(
    current_user: AuthenticatedUser,
    employees,
) -> None:
    """Create one employee, checklist, and linked login account."""

    st.subheader("Add Employee")
    st.caption(
        "All employee and account values are entered in one form. "
        "The Email field is also used as the login email."
    )

    managers = _manager_options(employees)

    with st.form(
        "employee_master_create_form",
        clear_on_submit=True,
    ):
        with st.container(
            border=True,
            key="employee_create_information_card",
        ):
            st.markdown("### Employee Information")

            number_column, _ = st.columns(
                [1.0, 5.0]
            )
            with number_column:
                employee_number = st.text_input(
                    "Employee Number *",
                    max_chars=80,
                )

            last_column, first_column, middle_column, suffix_column = (
                st.columns(4)
            )

            with last_column:
                last_name = st.text_input(
                    "Last Name *",
                    max_chars=100,
                )

            with first_column:
                first_name = st.text_input(
                    "First Name *",
                    max_chars=100,
                )

            with middle_column:
                middle_name = st.text_input(
                    "Middle Name",
                    max_chars=100,
                )

            with suffix_column:
                suffix = st.text_input(
                    "Suffix",
                    max_chars=30,
                )

            email_column, telephone_column, _ = st.columns(
                [2.0, 2.0, 2.0]
            )
            with email_column:
                email = st.text_input(
                    "Email *",
                    max_chars=255,
                )

            with telephone_column:
                telephone_mobile_no = st.text_input(
                    "Telephone / Mobile No.",
                    max_chars=50,
                )

            status_column, hire_column, _ = st.columns(
                [1.4, 0.8, 3.8]
            )

            with status_column:
                status_label = st.selectbox(
                    "Employment Status",
                    options=list(
                        EMPLOYMENT_STATUS_OPTIONS
                    ),
                    help=(
                        "Employed keeps the login account active. "
                        "Resigned automatically deactivates the account."
                    ),
                )

            with hire_column:
                hire_date = st.date_input(
                    "Hire Date",
                    value=date.today(),
                )

            department_column, manager_column, position_column = (
                st.columns(3)
            )

            with department_column:
                department_name = st.text_input(
                    "Department",
                    max_chars=150,
                    help=(
                        "Enter an existing or new department name. "
                        "Matching is case-insensitive, and a new department "
                        "record is created automatically when needed."
                    ),
                )

            with manager_column:
                manager_label = st.selectbox(
                    "Manager",
                    options=list(managers),
                )

            with position_column:
                job_title = st.text_input(
                    "Job Title / Position",
                    max_chars=150,
                )

            st.markdown("### Training Checklist")
            training_text = st.text_area(
                "Training",
                height=150,
                placeholder=(
                    "[x] Company Orientation\n"
                    "[ ] Data Privacy Training\n"
                    "[ ] Safety Training"
                ),
                help=(
                    "Use one training per line. [x] means completed and "
                    "[ ] means pending."
                ),
            )

        with st.container(
            border=True,
            key="employee_create_account_card",
        ):
            st.markdown("### Account Information")

            user_id_column, clearance_column = st.columns(2)

            with user_id_column:
                st.text_input(
                    "User ID",
                    value="Generated automatically after saving",
                    disabled=True,
                )

            with clearance_column:
                clearance_label = st.selectbox(
                    "Clearance *",
                    options=[
                        "1 - Admin",
                        "2 - User",
                    ],
                    index=1,
                )

            username_column, password_column = st.columns(2)

            with username_column:
                username = st.text_input(
                    "User Name *",
                    max_chars=100,
                )

            with password_column:
                temporary_password = st.text_input(
                    "Temporary Password *",
                    type="password",
                    max_chars=128,
                    help=(
                        "The employee must change this password "
                        "during first login."
                    ),
                )

        submitted = st.form_submit_button(
            "Create Employee Record",
            type="primary",
            use_container_width=True,
        )

    if not submitted:
        return

    try:
        request = EmployeeAccountCreate(
            company_id=current_user.company_id,
            employee_number=employee_number.strip(),
            last_name=last_name.strip(),
            first_name=first_name.strip(),
            middle_name=middle_name.strip() or None,
            suffix=suffix.strip() or None,
            job_title=job_title.strip() or None,
            department_name=(
                department_name.strip()
                or None
            ),
            manager_id=managers[manager_label],
            work_email=email.strip(),
            telephone_mobile_no=(
                telephone_mobile_no.strip()
                or None
            ),
            employment_status=(
                EMPLOYMENT_STATUS_OPTIONS[
                    status_label
                ]
            ),
            hire_date=hire_date,
            trainings=_parse_training_text(
                training_text
            ),
            create_login_account=True,
            username=username.strip(),
            login_email=email.strip(),
            temporary_password=temporary_password,
            clearance=int(clearance_label[0]),
        )

        with st.spinner(
            "Creating employee record and login account…"
        ):
            with SessionFactory() as session:
                employee = AdminManagementService(
                    session
                ).create_employee_with_optional_account(
                    request
                )

        set_operation_feedback(
            "Employee record created successfully: "
            f"{employee.employee_number} — "
            f"{employee.full_name}"
        )
        st.rerun()

    except ValidationError as error:
        st.error(_validation_message(error))
    except ValueError as error:
        st.error(str(error))
    except Exception:
        st.error(
            "The employee record could not be created. "
            "Check the employee number, username, and email."
        )


def _render_delete_employee(
    current_user: AuthenticatedUser,
    *,
    employee_id: int,
    employee_number: str,
    full_name: str,
    user_id: int | None,
) -> None:
    """Delete the currently selected employee after one acknowledgment."""

    st.divider()

    with st.expander(
        "Danger Zone — Delete Employee Record",
        expanded=False,
    ):
        st.warning(
            "Permanent deletion removes the employee profile, training "
            "records, and linked login account. This action cannot be "
            "undone. Department records are preserved."
        )

        if user_id == current_user.user_id:
            st.info(
                "Your own active administrator employee/account cannot "
                "be deleted while you are signed in."
            )
            return

        st.caption(
            "Selected employee to delete: "
            f"{employee_number} — {full_name}"
        )

        acknowledged = st.checkbox(
            "I understand that this permanently deletes the selected "
            "employee record and linked login account.",
            key=(
                "employee_delete_acknowledged_"
                f"{employee_id}"
            ),
        )

        delete_submitted = st.button(
            "Delete Employee Permanently",
            type="primary",
            use_container_width=True,
            disabled=not acknowledged,
            key=(
                "employee_delete_button_"
                f"{employee_id}"
            ),
        )

        if not delete_submitted:
            return

        try:
            request = EmployeeDeleteRequest(
                company_id=current_user.company_id,
                employee_id=employee_id,
                permanent_delete_acknowledged=acknowledged,
            )

            with st.spinner(
                "Permanently deleting employee record…"
            ):
                with SessionFactory() as session:
                    result = AdminManagementService(
                        session
                    ).delete_employee_master_record(
                        request,
                        current_user_id=current_user.user_id,
                    )

            st.session_state.pop(
                "employee_master_edit_selection",
                None,
            )
            st.session_state.pop(
                "employee_delete_acknowledged_"
                f"{employee_id}",
                None,
            )

            set_operation_feedback(
                "Employee permanently deleted: "
                f"{result.employee_number} — "
                f"{result.full_name}"
            )
            st.rerun()

        except ValidationError as error:
            st.error(_validation_message(error))
        except ValueError as error:
            st.error(str(error))
        except Exception:
            st.error(
                "The employee record could not be deleted. "
                "No deletion was completed."
            )

def _render_edit_employee(
    current_user: AuthenticatedUser,
    employees,
) -> None:
    """Edit or permanently delete one employee master record."""

    st.subheader("Edit Employee")
    st.caption(
        "Every displayed employee field is editable. Leave New Temporary "
        "Password blank to keep the current password."
    )

    if not employees:
        st.info("There is no employee available to edit.")
        return

    employee_options = {
        (
            f"{employee.employee_number} — "
            f"{employee.full_name}"
        ): employee.id
        for employee in employees
    }

    selected_label = st.selectbox(
        "Select Employee",
        options=list(employee_options),
        key="employee_master_edit_selection",
    )

    selected_id = employee_options[selected_label]

    with SessionFactory() as session:
        selected = AdminManagementService(
            session
        ).get_employee(
            company_id=current_user.company_id,
            employee_id=selected_id,
        )

        values = {
            "employee_number": selected.employee_number,
            "full_name": selected.full_name,
            "last_name": selected.last_name,
            "first_name": selected.first_name,
            "middle_name": selected.middle_name or "",
            "suffix": selected.suffix or "",
            "email": selected.work_email or "",
            "telephone_mobile_no": (
                selected.telephone_mobile_no or ""
            ),
            "job_title": selected.job_title or "",
            "department": (
                selected.department.name
                if selected.department
                else ""
            ),
            "manager_id": selected.manager_id,
            "status": selected.employment_status,
            "hire_date": selected.hire_date or date.today(),
            "training": _training_editor_value(selected),
            "user_id": (
                selected.user.id
                if selected.user
                else None
            ),
            "username": (
                selected.user.username
                if selected.user
                else ""
            ),
            "clearance": (
                selected.user.clearance
                if selected.user
                else 2
            ),
        }

    managers = _manager_options(
        employees,
        exclude_employee_id=selected_id,
    )

    manager_index = 0
    for index, manager_id in enumerate(
        managers.values()
    ):
        if manager_id == values["manager_id"]:
            manager_index = index
            break

    with st.form(
        f"employee_master_edit_form_{selected_id}"
    ):
        with st.container(
            border=True,
            key=f"employee_edit_information_card_{selected_id}",
        ):
            st.markdown("### Employee Information")

            number_column, _ = st.columns(
                [1.0, 5.0]
            )
            with number_column:
                employee_number = st.text_input(
                    "Employee Number *",
                    value=values["employee_number"],
                    max_chars=80,
                )

            last_column, first_column, middle_column, suffix_column = (
                st.columns(4)
            )

            with last_column:
                last_name = st.text_input(
                    "Last Name *",
                    value=values["last_name"],
                    max_chars=100,
                )

            with first_column:
                first_name = st.text_input(
                    "First Name *",
                    value=values["first_name"],
                    max_chars=100,
                )

            with middle_column:
                middle_name = st.text_input(
                    "Middle Name",
                    value=values["middle_name"],
                    max_chars=100,
                )

            with suffix_column:
                suffix = st.text_input(
                    "Suffix",
                    value=values["suffix"],
                    max_chars=30,
                )

            email_column, telephone_column, _ = st.columns(
                [2.0, 2.0, 2.0]
            )
            with email_column:
                email = st.text_input(
                    "Email *",
                    value=values["email"],
                    max_chars=255,
                )

            with telephone_column:
                telephone_mobile_no = st.text_input(
                    "Telephone / Mobile No.",
                    value=values["telephone_mobile_no"],
                    max_chars=50,
                )

            status_labels = list(
                EMPLOYMENT_STATUS_OPTIONS
            )
            current_status_label = (
                "Employed — Account Active"
                if values["status"] == "employed"
                else "Resigned — Account Inactive"
            )

            status_column, hire_column, _ = st.columns(
                [1.4, 0.8, 3.8]
            )

            with status_column:
                status_label = st.selectbox(
                    "Employment Status",
                    options=status_labels,
                    index=status_labels.index(
                        current_status_label
                    ),
                    help=(
                        "Changing to Resigned deactivates the login account. "
                        "Changing back to Employed reactivates it."
                    ),
                )

            with hire_column:
                hire_date = st.date_input(
                    "Hire Date",
                    value=values["hire_date"],
                )

            department_column, manager_column, position_column = (
                st.columns(3)
            )

            with department_column:
                department_name = st.text_input(
                    "Department",
                    value=values["department"],
                    max_chars=150,
                    help=(
                        "Edit the department directly. Existing names are "
                        "reused case-insensitively; new names create "
                        "department records automatically."
                    ),
                )

            with manager_column:
                manager_label = st.selectbox(
                    "Manager",
                    options=list(managers),
                    index=manager_index,
                )

            with position_column:
                job_title = st.text_input(
                    "Job Title / Position",
                    value=values["job_title"],
                    max_chars=150,
                )

            st.markdown("### Training Checklist")
            training_text = st.text_area(
                "Training",
                value=values["training"],
                height=180,
                help=(
                    "Use [x] for completed and [ ] for pending."
                ),
            )

        with st.container(
            border=True,
            key=f"employee_edit_account_card_{selected_id}",
        ):
            st.markdown("### Account Information")

            user_id_column, clearance_column = st.columns(2)

            with user_id_column:
                st.text_input(
                    "User ID",
                    value=(
                        str(values["user_id"])
                        if values["user_id"] is not None
                        else "Will be generated"
                    ),
                    disabled=True,
                )

            with clearance_column:
                clearance_label = st.selectbox(
                    "Clearance *",
                    options=[
                        "1 - Admin",
                        "2 - User",
                    ],
                    index=(
                        0
                        if values["clearance"] == 1
                        else 1
                    ),
                )

            username_column, password_column = st.columns(2)

            with username_column:
                username = st.text_input(
                    "User Name *",
                    value=values["username"],
                    max_chars=100,
                )

            with password_column:
                new_password = st.text_input(
                    "New Temporary Password",
                    type="password",
                    max_chars=128,
                    help=(
                        "Leave blank to keep the current password. "
                        "A newly set password must be changed at next login."
                    ),
                )

        submitted = st.form_submit_button(
            "Save Employee Changes",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        try:
            request = EmployeeMasterUpdate(
                company_id=current_user.company_id,
                employee_id=selected_id,
                employee_number=employee_number.strip(),
                last_name=last_name.strip(),
                first_name=first_name.strip(),
                middle_name=middle_name.strip() or None,
                suffix=suffix.strip() or None,
                work_email=email.strip(),
                telephone_mobile_no=(
                    telephone_mobile_no.strip()
                    or None
                ),
                job_title=job_title.strip() or None,
                department_name=(
                    department_name.strip()
                    or None
                ),
                manager_id=managers[manager_label],
                employment_status=(
                    EMPLOYMENT_STATUS_OPTIONS[
                        status_label
                    ]
                ),
                hire_date=hire_date,
                trainings=_parse_training_text(
                    training_text
                ),
                username=username.strip(),
                clearance=int(clearance_label[0]),
                new_temporary_password=(
                    new_password
                    if new_password
                    else None
                ),
            )

            with st.spinner(
                "Saving employee changes…"
            ):
                with SessionFactory() as session:
                    employee = AdminManagementService(
                        session
                    ).update_employee_master_record(
                        request,
                        current_user_id=current_user.user_id,
                    )

            set_operation_feedback(
                "Employee record updated successfully: "
                f"{employee.employee_number} — "
                f"{employee.full_name}"
            )
            st.rerun()

        except ValidationError as error:
            st.error(_validation_message(error))
        except ValueError as error:
            st.error(str(error))
        except Exception:
            st.error(
                "The employee record could not be updated. "
                "Check the employee number, username, and email."
            )

    _render_delete_employee(
        current_user,
        employee_id=selected_id,
        employee_number=values["employee_number"],
        full_name=values["full_name"],
        user_id=values["user_id"],
    )


def render_employees_page(
    current_user: AuthenticatedUser,
) -> None:
    """Render the complete Employee Master Record workspace."""

    st.title("Employees")
    st.caption(
        "Manage employee information, training, login account, and "
        "clearance in one place."
    )

    # Show the completed result after Streamlit refreshes the page.
    render_operation_feedback()

    with SessionFactory() as session:
        employees = AdminManagementService(
            session
        ).list_employees(current_user.company_id)

    list_tab, add_tab, edit_tab = st.tabs(
        [
            "Employee List",
            "Add Employee",
            "Edit Employee",
        ]
    )

    with list_tab:
        _render_employee_list(employees)

    with add_tab:
        _render_add_employee(
            current_user,
            employees,
        )

    with edit_tab:
        _render_edit_employee(
            current_user,
            employees,
        )
