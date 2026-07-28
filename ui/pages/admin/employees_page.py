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
    """Convert complete employee models into the requested table format."""

    return [
        {
            "Employee Number": employee.employee_number,
            "Full Name": employee.full_name,
            "Last Name": employee.last_name,
            "First Name": employee.first_name,
            "Middle Name": employee.middle_name or "",
            "Suffix": employee.suffix or "",
            "Job Title / Position": employee.job_title or "",
            "Department": (
                employee.department.name
                if employee.department
                else ""
            ),
            "Manager": (
                employee.manager.full_name
                if employee.manager
                else ""
            ),
            "Email": employee.work_email or "",
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
    """Render a safe responsive table with wrapping in every cell."""

    headers = list(rows[0].keys())

    header_html = "".join(
        f"<th>{escape(header)}</th>"
        for header in headers
    )

    body_rows: list[str] = []

    for row in rows:
        cells = "".join(
            f"<td>{_html_cell(row.get(header, ''))}</td>"
            for header in headers
        )

        body_rows.append(
            f"<tr>{cells}</tr>"
        )

    table_html = f"""
    <style>
        .employee-table-shell {{
            width: 100%;
            overflow-x: auto;
            border: 1px solid var(--hr-border);
            border-radius: 14px;
            background: var(--hr-surface);
        }}

        .employee-master-table {{
            width: 100%;
            min-width: 1900px;
            border-collapse: separate;
            border-spacing: 0;
            table-layout: fixed;
            font-size: 0.88rem;
        }}

        .employee-master-table th {{
            position: sticky;
            top: 0;
            z-index: 2;
            padding: 12px 14px;
            border-right: 1px solid var(--hr-border);
            border-bottom: 1px solid var(--hr-border);
            background: var(--hr-surface);
            color: var(--hr-text-primary);
            text-align: left;
            vertical-align: top;
            white-space: normal;
            overflow-wrap: anywhere;
            word-break: break-word;
            line-height: 1.35;
        }}

        .employee-master-table td {{
            padding: 12px 14px;
            border-right: 1px solid var(--hr-border);
            border-bottom: 1px solid var(--hr-border);
            color: var(--hr-text-secondary);
            text-align: left;
            vertical-align: top;
            white-space: normal;
            overflow-wrap: anywhere;
            word-break: break-word;
            line-height: 1.45;
            transition:
                color 0.14s ease,
                background-color 0.14s ease;
        }}

        .employee-master-table th:last-child,
        .employee-master-table td:last-child {{
            border-right: 0;
        }}

        .employee-master-table tbody tr:last-child td {{
            border-bottom: 0;
        }}

        .employee-master-table tbody tr:hover td {{
            color: var(--hr-text-primary);
            background: var(--hr-primary-soft);
        }}

        .employee-master-table th:nth-child(1),
        .employee-master-table td:nth-child(1) {{
            width: 125px;
        }}

        .employee-master-table th:nth-child(2),
        .employee-master-table td:nth-child(2) {{
            width: 190px;
        }}

        .employee-master-table th:nth-child(3),
        .employee-master-table td:nth-child(3),
        .employee-master-table th:nth-child(4),
        .employee-master-table td:nth-child(4) {{
            width: 135px;
        }}

        .employee-master-table th:nth-child(5),
        .employee-master-table td:nth-child(5),
        .employee-master-table th:nth-child(6),
        .employee-master-table td:nth-child(6) {{
            width: 115px;
        }}

        .employee-master-table th:nth-child(7),
        .employee-master-table td:nth-child(7),
        .employee-master-table th:nth-child(8),
        .employee-master-table td:nth-child(8),
        .employee-master-table th:nth-child(9),
        .employee-master-table td:nth-child(9) {{
            width: 165px;
        }}

        .employee-master-table th:nth-child(10),
        .employee-master-table td:nth-child(10) {{
            width: 210px;
        }}

        .employee-master-table th:nth-child(11),
        .employee-master-table td:nth-child(11) {{
            width: 110px;
        }}

        .employee-master-table th:nth-child(12),
        .employee-master-table td:nth-child(12) {{
            width: 230px;
        }}

        .employee-master-table th:nth-child(13),
        .employee-master-table td:nth-child(13) {{
            width: 245px;
        }}
    </style>

    <div class="employee-table-shell">
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
    """Display the employee table with wrapping inside every cell."""

    st.subheader("Employee List")
    st.caption(
        "Every cell wraps automatically. Employment Status also shows "
        "whether the linked account is active or inactive."
    )

    rows = _employee_rows(employees)

    if not rows:
        st.info("No employee records were found.")
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
        st.markdown("#### Employee Information")

        left, middle, right = st.columns(3)

        with left:
            employee_number = st.text_input(
                "Employee Number *",
                max_chars=80,
            )
            last_name = st.text_input(
                "Last Name *",
                max_chars=100,
            )
            first_name = st.text_input(
                "First Name *",
                max_chars=100,
            )

        with middle:
            middle_name = st.text_input(
                "Middle Name",
                max_chars=100,
            )
            suffix = st.text_input(
                "Suffix",
                max_chars=30,
            )
            email = st.text_input(
                "Email *",
                max_chars=255,
            )

        with right:
            job_title = st.text_input(
                "Job Title / Position",
                max_chars=150,
            )
            department_name = st.text_input(
                "Department",
                max_chars=150,
                help=(
                    "Enter an existing or new department name. "
                    "Matching is case-insensitive, and a new department "
                    "record is created automatically when needed."
                ),
            )
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

        manager_label = st.selectbox(
            "Manager",
            options=list(managers),
        )

        hire_date = st.date_input(
            "Hire Date",
            value=date.today(),
        )

        st.markdown("#### Training Checklist")
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

        st.markdown("#### Account Information")

        account_left, account_right = st.columns(2)

        with account_left:
            username = st.text_input(
                "User Name *",
                max_chars=100,
            )
            temporary_password = st.text_input(
                "Temporary Password *",
                type="password",
                max_chars=128,
                help=(
                    "The employee must change this password "
                    "during first login."
                ),
            )

        with account_right:
            clearance_label = st.selectbox(
                "Clearance *",
                options=[
                    "1 - Admin",
                    "2 - User",
                ],
                index=1,
            )
            st.text_input(
                "User ID",
                value="Generated automatically after saving",
                disabled=True,
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
    """Render the protected permanent-delete action."""

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
            f"Selected employee: {employee_number} — {full_name}"
        )

        with st.form(
            f"employee_delete_form_{employee_id}",
            clear_on_submit=False,
        ):
            confirmation_number = st.text_input(
                "Type the exact Employee Number to confirm",
                placeholder=employee_number,
                max_chars=80,
                key=(
                    "employee_delete_confirmation_"
                    f"{employee_id}"
                ),
            )

            acknowledged = st.checkbox(
                "I understand that this permanently deletes the "
                "employee record and linked login account.",
                key=(
                    "employee_delete_acknowledged_"
                    f"{employee_id}"
                ),
            )

            delete_submitted = st.form_submit_button(
                "Delete Employee Permanently",
                use_container_width=True,
            )

        if not delete_submitted:
            return

        try:
            request = EmployeeDeleteRequest(
                company_id=current_user.company_id,
                employee_id=employee_id,
                confirmation_employee_number=(
                    confirmation_number
                ),
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
        st.markdown("#### Employee Information")

        left, middle, right = st.columns(3)

        with left:
            employee_number = st.text_input(
                "Employee Number *",
                value=values["employee_number"],
                max_chars=80,
            )
            last_name = st.text_input(
                "Last Name *",
                value=values["last_name"],
                max_chars=100,
            )
            first_name = st.text_input(
                "First Name *",
                value=values["first_name"],
                max_chars=100,
            )

        with middle:
            middle_name = st.text_input(
                "Middle Name",
                value=values["middle_name"],
                max_chars=100,
            )
            suffix = st.text_input(
                "Suffix",
                value=values["suffix"],
                max_chars=30,
            )
            email = st.text_input(
                "Email *",
                value=values["email"],
                max_chars=255,
            )

        with right:
            job_title = st.text_input(
                "Job Title / Position",
                value=values["job_title"],
                max_chars=150,
            )
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
            status_labels = list(
                EMPLOYMENT_STATUS_OPTIONS
            )
            current_status_label = (
                "Employed — Account Active"
                if values["status"] == "employed"
                else "Resigned — Account Inactive"
            )
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

        manager_label = st.selectbox(
            "Manager",
            options=list(managers),
            index=manager_index,
        )

        hire_date = st.date_input(
            "Hire Date",
            value=values["hire_date"],
        )

        st.markdown("#### Training Checklist")
        training_text = st.text_area(
            "Training",
            value=values["training"],
            height=180,
            help=(
                "Use [x] for completed and [ ] for pending."
            ),
        )

        st.markdown("#### Account Information")

        account_left, account_right = st.columns(2)

        with account_left:
            st.text_input(
                "User ID",
                value=(
                    str(values["user_id"])
                    if values["user_id"] is not None
                    else "Will be generated"
                ),
                disabled=True,
            )
            username = st.text_input(
                "User Name *",
                value=values["username"],
                max_chars=100,
            )

        with account_right:
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
