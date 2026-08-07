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

GENDER_OPTIONS = ["Male", "Female"]
CIVIL_STATUS_OPTIONS = [
    "N/A",
    "Single",
    "Married",
    "Widowed",
    "Separated",
    "Divorced",
]
MISSING_VALUE_TOKENS = {"", "n/a", "na", "none", "null", "-", "—"}


def _optional_value(value: str | None) -> str | None:
    """Normalize blank and N/A-like optional form values to ``None``."""

    if value is None:
        return None

    normalized = str(value).strip()
    if normalized.casefold() in MISSING_VALUE_TOKENS:
        return None
    return normalized


def _display_value(value: object) -> str:
    """Display one missing table/detail value consistently as N/A."""

    if value is None:
        return "N/A"
    text = str(value).strip()
    return text if text and text.casefold() not in MISSING_VALUE_TOKENS else "N/A"


def _calculate_age(date_of_birth: date | None) -> int | None:
    """Calculate current age without storing a value that becomes stale."""

    if date_of_birth is None:
        return None
    today = date.today()
    return (
        today.year
        - date_of_birth.year
        - ((today.month, today.day) < (date_of_birth.month, date_of_birth.day))
    )


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
        return "N/A"

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
        return "N/A"

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
    """Build employee rows with consistent N/A and clean full names."""

    rows: list[dict[str, object]] = []
    for employee in employees:
        rows.append(
            {
                "Employee Number": _display_value(employee.employee_number),
                "Full Name": employee.full_name or "N/A",
                "Job Title / Position": _display_value(employee.job_title),
                "Department": _display_value(
                    employee.department.name if employee.department else None
                ),
                "Manager": _display_value(
                    employee.manager.full_name if employee.manager else None
                ),
                "Leader": _display_value(
                    employee.leader.full_name if employee.leader else None
                ),
                "Gender": _display_value(employee.gender),
                "Civil Status": _display_value(employee.civil_status),
                "Date of Birth": (
                    employee.date_of_birth.isoformat()
                    if employee.date_of_birth
                    else "N/A"
                ),
                "Age": _display_value(employee.age),
                "Email / Telephone / Mobile No.": (
                    f"Email: {_display_value(employee.work_email)}\n"
                    f"Tel/Mobile: {_display_value(employee.telephone_mobile_no)}"
                ),
                "Status": (
                    "Employed\nAccount Active"
                    if employee.employment_status == "employed"
                    else "Resigned\nAccount Inactive"
                ),
                "Training": _training_cell(employee),
                "Account": _account_cell(employee),
            }
        )
    return rows

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
            employee.leader.full_name
            if employee.leader
            else ""
        ),
        employee.gender,
        employee.civil_status,
        employee.date_of_birth,
        employee.age,
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


def _assignment_options(
    employees,
    *,
    empty_label: str,
    exclude_employee_id: int | None = None,
) -> dict[str, int | None]:
    """Return employee choices with a role-specific empty option label."""

    return {
        empty_label: None,
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


def _manager_options(
    employees,
    *,
    exclude_employee_id: int | None = None,
) -> dict[str, int | None]:
    """Return manager choices with the correct empty-state label."""

    return _assignment_options(
        employees,
        empty_label="No Manager",
        exclude_employee_id=exclude_employee_id,
    )


def _leader_options(
    employees,
    *,
    exclude_employee_id: int | None = None,
) -> dict[str, int | None]:
    """Return leader choices with the correct empty-state label."""

    return _assignment_options(
        employees,
        empty_label="No Leader",
        exclude_employee_id=exclude_employee_id,
    )


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
            min-width: 2440px;
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
        .employee-master-table td:nth-child(1) {{ width: 130px; }}

        .employee-master-table th:nth-child(2),
        .employee-master-table td:nth-child(2) {{ width: 180px; }}

        .employee-master-table th:nth-child(3),
        .employee-master-table td:nth-child(3) {{ width: 165px; }}

        .employee-master-table th:nth-child(4),
        .employee-master-table td:nth-child(4) {{ width: 145px; }}

        .employee-master-table th:nth-child(5),
        .employee-master-table td:nth-child(5) {{ width: 165px; }}

        .employee-master-table th:nth-child(6),
        .employee-master-table td:nth-child(6) {{ width: 165px; }}

        .employee-master-table th:nth-child(7),
        .employee-master-table td:nth-child(7) {{ width: 125px; }}

        .employee-master-table th:nth-child(8),
        .employee-master-table td:nth-child(8) {{ width: 145px; }}

        .employee-master-table th:nth-child(9),
        .employee-master-table td:nth-child(9) {{ width: 145px; }}

        .employee-master-table th:nth-child(10),
        .employee-master-table td:nth-child(10) {{ width: 90px; }}

        .employee-master-table th:nth-child(11),
        .employee-master-table td:nth-child(11) {{ width: 250px; }}

        .employee-master-table th:nth-child(12),
        .employee-master-table td:nth-child(12) {{ width: 150px; }}

        .employee-master-table th:nth-child(13),
        .employee-master-table td:nth-child(13) {{ width: 230px; }}

        .employee-master-table th:nth-child(14),
        .employee-master-table td:nth-child(14) {{ width: 240px; }}
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
    """Create one employee using the requested real-time profile layout."""

    st.subheader("Add Employee")
    st.caption(
        "All employee and account values are entered in one workspace. "
        "The Email field is also used as the login email."
    )

    manager_people = _manager_options(employees)
    leader_people = _leader_options(employees)

    with st.container(border=True, key="employee_create_information_card"):
        st.markdown("### Employee Information")

        number_column, _ = st.columns([1.0, 5.0])
        with number_column:
            employee_number = st.text_input(
                "Employee Number *", max_chars=80, key="create_employee_number"
            )

        last_column, first_column, middle_column, suffix_column = st.columns(4)
        with last_column:
            last_name = st.text_input(
                "Last Name *", max_chars=100, key="create_last_name"
            )
        with first_column:
            first_name = st.text_input(
                "First Name *", max_chars=100, key="create_first_name"
            )
        with middle_column:
            middle_name = st.text_input(
                "Middle Name", max_chars=100, key="create_middle_name"
            )
        with suffix_column:
            suffix = st.text_input(
                "Suffix", max_chars=30, key="create_suffix"
            )

        gender_column, civil_column, birth_column, age_column = st.columns(4)
        with gender_column:
            gender_label = st.selectbox(
                "Gender", options=GENDER_OPTIONS, key="create_gender"
            )
        with civil_column:
            civil_status_label = st.selectbox(
                "Civil Status",
                options=CIVIL_STATUS_OPTIONS,
                key="create_civil_status",
            )
        with birth_column:
            date_of_birth = st.date_input(
                "Date of Birth",
                value=None,
                min_value=date(1900, 1, 1),
                max_value=date.today(),
                key="create_date_of_birth",
            )
        with age_column:
            st.text_input(
                "Age",
                value=_display_value(_calculate_age(date_of_birth)),
                disabled=True,
                key=f"create_age_display_{date_of_birth or 'none'}",
            )

        email_column, telephone_column, _ = st.columns([2.0, 2.0, 2.0])
        with email_column:
            email = st.text_input(
                "Email *", max_chars=255, key="create_email"
            )
        with telephone_column:
            telephone_mobile_no = st.text_input(
                "Telephone / Mobile No.",
                max_chars=50,
                key="create_telephone_mobile",
            )

        department_column, manager_column, leader_column, position_column = st.columns(4)
        with department_column:
            department_name = st.text_input(
                "Department",
                max_chars=150,
                key="create_department",
                help=(
                    "Enter an existing or new department name. Matching is "
                    "case-insensitive, and a new department record is created "
                    "automatically when needed."
                ),
            )
        with manager_column:
            manager_label = st.selectbox(
                "Manager", options=list(manager_people), key="create_manager"
            )
        with leader_column:
            leader_label = st.selectbox(
                "Leader", options=list(leader_people), key="create_leader"
            )
        with position_column:
            job_title = st.text_input(
                "Job Title / Position",
                max_chars=150,
                key="create_job_title",
            )

        status_column, hire_column, _ = st.columns([1.4, 0.8, 3.8])
        with status_column:
            status_label = st.selectbox(
                "Employment Status",
                options=list(EMPLOYMENT_STATUS_OPTIONS),
                key="create_employment_status",
                help=(
                    "Employed keeps the login account active. Resigned "
                    "automatically deactivates the account."
                ),
            )
        with hire_column:
            hire_date = st.date_input(
                "Hire Date", value=date.today(), key="create_hire_date"
            )

        st.markdown("### Training Checklist")
        training_text = st.text_area(
            "Training",
            height=150,
            key="create_training",
            placeholder=(
                "[x] Company Orientation\n"
                "[ ] Data Privacy Training\n"
                "[ ] Safety Training"
            ),
            help="Use one training per line. [x] means completed and [ ] means pending.",
        )

    with st.container(border=True, key="employee_create_account_card"):
        st.markdown("### Account Information")
        user_id_column, clearance_column = st.columns(2)
        with user_id_column:
            st.text_input(
                "User ID",
                value="Generated automatically after saving",
                disabled=True,
                key="create_user_id_display",
            )
        with clearance_column:
            clearance_label = st.selectbox(
                "Clearance *",
                options=["1 - Admin", "2 - User"],
                index=1,
                key="create_clearance",
            )

        username_column, password_column = st.columns(2)
        with username_column:
            username = st.text_input(
                "User Name *", max_chars=100, key="create_username"
            )
        with password_column:
            temporary_password = st.text_input(
                "Temporary Password *",
                type="password",
                max_chars=128,
                key="create_temporary_password",
                help="The employee must change this password during first login.",
            )

    submitted = st.button(
        "Create Employee Record",
        type="primary",
        use_container_width=True,
        key="create_employee_submit",
    )

    if not submitted:
        return

    try:
        request = EmployeeAccountCreate(
            company_id=current_user.company_id,
            employee_number=employee_number.strip(),
            last_name=last_name.strip(),
            first_name=first_name.strip(),
            middle_name=_optional_value(middle_name),
            suffix=_optional_value(suffix),
            job_title=_optional_value(job_title),
            department_name=_optional_value(department_name),
            manager_id=manager_people[manager_label],
            leader_id=leader_people[leader_label],
            work_email=email.strip(),
            telephone_mobile_no=_optional_value(telephone_mobile_no.strip()),
            gender=_optional_value(gender_label),
            civil_status=_optional_value(civil_status_label),
            date_of_birth=date_of_birth,
            employment_status=EMPLOYMENT_STATUS_OPTIONS[status_label],
            hire_date=hire_date,
            trainings=_parse_training_text(training_text),
            create_login_account=True,
            username=username.strip(),
            login_email=email.strip(),
            temporary_password=temporary_password,
            clearance=int(clearance_label[0]),
        )

        with st.spinner("Creating employee record and login account…"):
            with SessionFactory() as session:
                employee = AdminManagementService(
                    session
                ).create_employee_with_optional_account(request)

        set_operation_feedback(
            "Employee record created successfully: "
            f"{employee.employee_number} — {employee.full_name}"
        )
        for key in list(st.session_state):
            if key.startswith("create_"):
                del st.session_state[key]
        st.rerun()
    except ValidationError as error:
        st.error(_validation_message(error))
    except ValueError as error:
        st.error(str(error))


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
    """Edit employee profile with real-time age calculation."""

    st.subheader("Edit Employee")
    st.caption(
        "Every displayed employee field is editable. Leave New Temporary "
        "Password blank to keep the current password."
    )
    if not employees:
        st.info("There is no employee available to edit.")
        return

    employee_options = {
        f"{employee.employee_number} — {employee.full_name}": employee.id
        for employee in employees
    }
    selected_label = st.selectbox(
        "Select Employee",
        options=list(employee_options),
        key="employee_master_edit_selection",
    )
    selected_id = employee_options[selected_label]

    with SessionFactory() as session:
        selected = AdminManagementService(session).get_employee(
            company_id=current_user.company_id,
            employee_id=selected_id,
        )
        values = {
            "employee_number": selected.employee_number,
            "last_name": selected.last_name,
            "first_name": selected.first_name,
            "middle_name": selected.middle_name or "",
            "suffix": selected.suffix or "",
            "email": selected.work_email or "",
            "telephone_mobile_no": selected.telephone_mobile_no or "",
            "job_title": selected.job_title or "",
            "department": selected.department.name if selected.department else "",
            "manager_id": selected.manager_id,
            "leader_id": selected.leader_id,
            "gender": selected.gender or "N/A",
            "civil_status": selected.civil_status or "N/A",
            "date_of_birth": selected.date_of_birth,
            "status": selected.employment_status,
            "hire_date": selected.hire_date or date.today(),
            "training": _training_editor_value(selected),
            "user_id": selected.user.id if selected.user else None,
            "username": selected.user.username if selected.user else "",
            "clearance": selected.user.clearance if selected.user else 2,
        }

    manager_people = _manager_options(
        employees, exclude_employee_id=selected_id
    )
    leader_people = _leader_options(
        employees, exclude_employee_id=selected_id
    )

    def option_index(
        options: dict[str, int | None],
        target_id: int | None,
    ) -> int:
        for index, person_id in enumerate(options.values()):
            if person_id == target_id:
                return index
        return 0

    prefix = f"edit_{selected_id}_"

    with st.container(border=True, key=f"employee_edit_information_card_{selected_id}"):
        st.markdown("### Employee Information")

        number_column, _ = st.columns([1.0, 5.0])
        with number_column:
            employee_number = st.text_input(
                "Employee Number *",
                value=values["employee_number"],
                max_chars=80,
                key=prefix + "employee_number",
            )

        last_column, first_column, middle_column, suffix_column = st.columns(4)
        with last_column:
            last_name = st.text_input(
                "Last Name *", value=values["last_name"], max_chars=100, key=prefix + "last_name"
            )
        with first_column:
            first_name = st.text_input(
                "First Name *", value=values["first_name"], max_chars=100, key=prefix + "first_name"
            )
        with middle_column:
            middle_name = st.text_input(
                "Middle Name", value=values["middle_name"], max_chars=100, key=prefix + "middle_name"
            )
        with suffix_column:
            suffix = st.text_input(
                "Suffix", value=values["suffix"], max_chars=30, key=prefix + "suffix"
            )

        gender_column, civil_column, birth_column, age_column = st.columns(4)
        with gender_column:
            gender_label = st.selectbox(
                "Gender",
                options=GENDER_OPTIONS,
                index=GENDER_OPTIONS.index(values["gender"]) if values["gender"] in GENDER_OPTIONS else 0,
                key=prefix + "gender",
            )
        with civil_column:
            civil_status_label = st.selectbox(
                "Civil Status",
                options=CIVIL_STATUS_OPTIONS,
                index=CIVIL_STATUS_OPTIONS.index(values["civil_status"]) if values["civil_status"] in CIVIL_STATUS_OPTIONS else 0,
                key=prefix + "civil_status",
            )
        with birth_column:
            date_of_birth = st.date_input(
                "Date of Birth",
                value=values["date_of_birth"],
                min_value=date(1900, 1, 1),
                max_value=date.today(),
                key=prefix + "date_of_birth",
            )
        with age_column:
            st.text_input(
                "Age",
                value=_display_value(_calculate_age(date_of_birth)),
                disabled=True,
                key=prefix + f"age_display_{date_of_birth or 'none'}",
            )

        email_column, telephone_column, _ = st.columns([2.0, 2.0, 2.0])
        with email_column:
            email = st.text_input(
                "Email *", value=values["email"], max_chars=255, key=prefix + "email"
            )
        with telephone_column:
            telephone_mobile_no = st.text_input(
                "Telephone / Mobile No.",
                value=values["telephone_mobile_no"],
                max_chars=50,
                key=prefix + "telephone_mobile",
            )

        department_column, manager_column, leader_column, position_column = st.columns(4)
        with department_column:
            department_name = st.text_input(
                "Department",
                value=values["department"],
                max_chars=150,
                key=prefix + "department",
                help=(
                    "Edit the department directly. Existing names are reused "
                    "case-insensitively; new names create department records automatically."
                ),
            )
        with manager_column:
            manager_label = st.selectbox(
                "Manager",
                options=list(manager_people),
                index=option_index(manager_people, values["manager_id"]),
                key=prefix + "manager",
            )
        with leader_column:
            leader_label = st.selectbox(
                "Leader",
                options=list(leader_people),
                index=option_index(leader_people, values["leader_id"]),
                key=prefix + "leader",
            )
        with position_column:
            job_title = st.text_input(
                "Job Title / Position",
                value=values["job_title"],
                max_chars=150,
                key=prefix + "job_title",
            )

        status_labels = list(EMPLOYMENT_STATUS_OPTIONS)
        current_status_label = (
            "Employed — Account Active"
            if values["status"] == "employed"
            else "Resigned — Account Inactive"
        )
        status_column, hire_column, _ = st.columns([1.4, 0.8, 3.8])
        with status_column:
            status_label = st.selectbox(
                "Employment Status",
                options=status_labels,
                index=status_labels.index(current_status_label),
                key=prefix + "employment_status",
                help=(
                    "Changing to Resigned deactivates the login account. "
                    "Changing back to Employed reactivates it."
                ),
            )
        with hire_column:
            hire_date = st.date_input(
                "Hire Date", value=values["hire_date"], key=prefix + "hire_date"
            )

        st.markdown("### Training Checklist")
        training_text = st.text_area(
            "Training",
            value=values["training"],
            height=180,
            key=prefix + "training",
            help="Use [x] for completed and [ ] for pending.",
        )

    with st.container(border=True, key=f"employee_edit_account_card_{selected_id}"):
        st.markdown("### Account Information")
        user_id_column, clearance_column = st.columns(2)
        with user_id_column:
            st.text_input(
                "User ID",
                value=str(values["user_id"]) if values["user_id"] is not None else "Will be generated",
                disabled=True,
                key=prefix + "user_id_display",
            )
        with clearance_column:
            clearance_label = st.selectbox(
                "Clearance *",
                options=["1 - Admin", "2 - User"],
                index=0 if values["clearance"] == 1 else 1,
                key=prefix + "clearance",
            )

        username_column, password_column = st.columns(2)
        with username_column:
            username = st.text_input(
                "User Name *", value=values["username"], max_chars=100, key=prefix + "username"
            )
        with password_column:
            new_password = st.text_input(
                "New Temporary Password",
                type="password",
                max_chars=128,
                key=prefix + "new_password",
                help="Leave blank to keep the current password.",
            )

    submitted = st.button(
        "Save Employee Changes",
        type="primary",
        use_container_width=True,
        key=prefix + "submit",
    )

    if not submitted:
        return

    try:
        request = EmployeeMasterUpdate(
            company_id=current_user.company_id,
            employee_id=selected_id,
            employee_number=employee_number.strip(),
            last_name=last_name.strip(),
            first_name=first_name.strip(),
            middle_name=_optional_value(middle_name),
            suffix=_optional_value(suffix),
            work_email=email.strip(),
            telephone_mobile_no=_optional_value(telephone_mobile_no.strip()),
            job_title=_optional_value(job_title),
            department_name=_optional_value(department_name),
            manager_id=manager_people[manager_label],
            leader_id=leader_people[leader_label],
            gender=_optional_value(gender_label),
            civil_status=_optional_value(civil_status_label),
            date_of_birth=date_of_birth,
            employment_status=EMPLOYMENT_STATUS_OPTIONS[status_label],
            hire_date=hire_date,
            trainings=_parse_training_text(training_text),
            username=username.strip(),
            clearance=int(clearance_label[0]),
            new_temporary_password=new_password or None,
        )

        with st.spinner("Saving employee changes…"):
            with SessionFactory() as session:
                employee = AdminManagementService(session).update_employee_master_record(
                    request, current_user_id=current_user.user_id
                )

        set_operation_feedback(
            "Employee record updated successfully: "
            f"{employee.employee_number} — {employee.full_name}"
        )
        st.rerun()
    except ValidationError as error:
        st.error(_validation_message(error))
    except ValueError as error:
        st.error(str(error))


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
