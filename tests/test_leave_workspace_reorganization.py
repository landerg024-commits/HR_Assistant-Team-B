"""Tests for Leave Overview and Credit Management separation."""

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from config.settings import Settings
from database.base import Base
from models.employee import Employee
from models.leave_request import LeaveRequest
from scripts.create_initial_data import seed_initial_data
from services.leave_service import LeaveService


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code="LEAVEWORK",
        initial_company_name="Leave Workspace Company",
        initial_admin_username="admin",
        initial_admin_email="leave.workspace@example.com",
        initial_admin_password=SecretStr("Temporary123!"),
        initial_admin_employee_number="ADMIN-001",
        initial_admin_first_name="System",
        initial_admin_last_name="Administrator",
        leave_attachment_dir=str(
            tmp_path / "leave_files"
        ),
        password_reset_outbox_dir=str(
            tmp_path / "outbox"
        ),
    )


def _factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )
    Base.metadata.create_all(engine)

    return sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )


def _create_employee_and_requests(
    session,
    seed,
    service: LeaveService,
) -> Employee:
    manager = seed["admin_employee"]
    manager.work_email = "manager@example.com"

    employee = Employee(
        company_id=seed["company"].id,
        manager_id=manager.id,
        employee_number="EMP-WORK-001",
        first_name="Ana",
        last_name="Reyes",
        work_email="ana.reyes@example.com",
        employment_status="employed",
    )
    session.add(employee)
    session.flush()

    leave_type = service.list_leave_types(
        seed["company"].id
    )[0]

    requests = [
        LeaveRequest(
            company_id=seed["company"].id,
            public_id="LRQ_2024",
            employee_id=employee.id,
            leave_type_id=leave_type.id,
            manager_employee_id=manager.id,
            start_date=date(2024, 6, 3),
            end_date=date(2024, 6, 4),
            requested_days=Decimal("2.00"),
            reason="2024 request",
            manager_email="manager@example.com",
            cc_emails_json="[]",
            email_status="sent",
            submitted_at=datetime(
                2024,
                5,
                20,
                tzinfo=timezone.utc,
            ),
        ),
        LeaveRequest(
            company_id=seed["company"].id,
            public_id="LRQ_2025",
            employee_id=employee.id,
            leave_type_id=leave_type.id,
            manager_employee_id=manager.id,
            start_date=date(2025, 7, 7),
            end_date=date(2025, 7, 8),
            requested_days=Decimal("2.00"),
            reason="2025 request",
            manager_email="manager@example.com",
            cc_emails_json="[]",
            email_status="sent",
            submitted_at=datetime(
                2025,
                6,
                20,
                tzinfo=timezone.utc,
            ),
        ),
        LeaveRequest(
            company_id=seed["company"].id,
            public_id="LRQ_CROSS_YEAR",
            employee_id=employee.id,
            leave_type_id=leave_type.id,
            manager_employee_id=manager.id,
            start_date=date(2025, 12, 31),
            end_date=date(2026, 1, 2),
            requested_days=Decimal("3.00"),
            reason="Cross-year request",
            manager_email="manager@example.com",
            cc_emails_json="[]",
            email_status="sent",
            submitted_at=datetime(
                2025,
                12,
                1,
                tzinfo=timezone.utc,
            ),
        ),
    ]

    session.add_all(requests)
    session.commit()

    return employee


def test_request_filter_uses_selected_leave_year(
    tmp_path: Path,
) -> None:
    factory = _factory()

    with factory() as session:
        settings = _settings(tmp_path)
        seed = seed_initial_data(session, settings)
        service = LeaveService(
            session,
            settings=settings,
        )
        _create_employee_and_requests(
            session,
            seed,
            service,
        )

        requests_2024 = service.list_company_requests(
            seed["company"].id,
            2024,
        )
        requests_2025 = service.list_company_requests(
            seed["company"].id,
            2025,
        )
        requests_2026 = service.list_company_requests(
            seed["company"].id,
            2026,
        )

        assert {
            item.public_id
            for item in requests_2024
        } == {"LRQ_2024"}
        assert {
            item.public_id
            for item in requests_2025
        } == {
            "LRQ_2025",
            "LRQ_CROSS_YEAR",
        }
        assert {
            item.public_id
            for item in requests_2026
        } == {"LRQ_CROSS_YEAR"}


def test_overview_metrics_use_selected_year(
    tmp_path: Path,
) -> None:
    factory = _factory()

    with factory() as session:
        settings = _settings(tmp_path)
        seed = seed_initial_data(session, settings)
        service = LeaveService(
            session,
            settings=settings,
        )
        _create_employee_and_requests(
            session,
            seed,
            service,
        )

        metrics_2024 = service.overview(
            seed["company"].id,
            2024,
        )
        metrics_2025 = service.overview(
            seed["company"].id,
            2025,
        )

        assert metrics_2024["total_requests"] == 1
        assert (
            metrics_2024["requests_submitted_in_year"]
            == 1
        )
        assert metrics_2025["total_requests"] == 2
        assert (
            metrics_2025["requests_submitted_in_year"]
            == 2
        )
        assert metrics_2025["employees_with_leave"] == 1


def test_tabs_use_simplified_workspace_names() -> None:
    source = (
        PROJECT_ROOT
        / "ui/pages/admin/leave_management_page.py"
    ).read_text(encoding="utf-8")

    assert '"Overview"' in source
    assert '"Employee Leave Accounts"' in source
    assert '"Leave Requests"' in source
    assert '"Leave Rules"' in source
    assert '"Credit Management"' not in source
    assert '"Leave Types & Rules"' not in source
    assert '"Leave Credits"' not in source


def test_leave_year_is_shared_above_tabs() -> None:
    source = (
        PROJECT_ROOT
        / "ui/pages/admin/leave_management_page.py"
    ).read_text(encoding="utf-8")

    page_block = source.split(
        "def render_admin_leave_management_page(",
        1,
    )[1]

    year_position = page_block.index(
        '"Leave Year"'
    )
    tabs_position = page_block.index(
        "st.tabs("
    )

    assert year_position < tabs_position
    assert "leave_management_year" in page_block
    assert (
        "The selected year applies to Overview"
        in page_block
    )


def test_overview_is_operational_dashboard_only() -> None:
    source = (
        PROJECT_ROOT
        / "ui/pages/admin/leave_management_page.py"
    ).read_text(encoding="utf-8")

    overview = source.split(
        "def _render_overview(",
        1,
    )[1].split(
        "def _render_employee_account_summary(",
        1,
    )[0]

    assert "Employees on Leave Today" in overview
    assert "Attention Needed" in overview
    assert "Recent Leave Requests" in overview
    assert "Save Leave Credits" not in overview
    assert "Transaction History" not in overview
    assert "_render_employee_account_summary(" not in overview
    assert "_render_credit_breakdown(" not in overview


def test_employee_accounts_combines_view_adjustment_and_history() -> None:
    source = (
        PROJECT_ROOT
        / "ui/pages/admin/leave_management_page.py"
    ).read_text(encoding="utf-8")

    assert "def _render_employee_accounts(" in source
    assert "Employee Leave Account" in source
    assert "Available Credits" in source
    assert '"Set Leave Credits"' in source
    assert '"Transaction History"' in source
    assert "Save Leave Credits" in source


def test_requests_receive_selected_year_and_filters() -> None:
    source = (
        PROJECT_ROOT
        / "ui/pages/admin/leave_management_page.py"
    ).read_text(encoding="utf-8")

    assert (
        "service.list_company_requests(\n"
        "            current_user.company_id,\n"
        "            selected_year,"
        in source
    )
    assert '"All Departments"' in source
    assert '"All Leave Types"' in source
    assert '"All Statuses"' in source
    assert '"Find Employee"' in source


def test_admin_request_page_remains_view_only() -> None:
    source = (
        PROJECT_ROOT
        / "ui/pages/admin/leave_management_page.py"
    ).read_text(encoding="utf-8")

    request_block = source.split(
        "def _render_request_details(",
        1,
    )[1].split(
        "def _render_requests(",
        1,
    )[0]

    assert "View-only" not in request_block
    assert "This page is view-only." in request_block
    assert "Approve" not in request_block
    assert "Reject" not in request_block
    assert "Cancel" not in request_block
