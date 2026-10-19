"""Create sample TXT policy files for local file-based testing.

Run:

    python scripts/create_sample_policies.py

The files are processed through the same parser, storage, document, and
section pipeline used by the administrator upload page.
"""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from config.settings import get_settings
from database.runtime_schema import initialize_runtime_schema
from database.session import SessionFactory
from repositories.company_repository import CompanyRepository
from repositories.user_repository import UserRepository
from schemas.policy_schema import PolicyUploadRequest
from services.policy_service import PolicyService


SAMPLE_POLICIES = (
    {
        "filename": "Annual_Leave_Policy.txt",
        "title": "Annual Leave Policy",
        "category": "Leave",
        "version": "1.1-file",
        "summary": (
            "Rules for annual leave entitlement, requests, "
            "approval, and unused balances."
        ),
        "content": """
ANNUAL LEAVE ENTITLEMENT:
Regular employees receive fifteen paid annual leave days per calendar year.

REQUEST PROCEDURE:
Employees should submit annual leave requests at least five working days
before the intended leave date. Requests require manager approval.

UNUSED LEAVE:
A maximum of five unused annual leave days may be carried into the next
calendar year.
""",
    },
    {
        "filename": "Attendance_and_Punctuality_Policy.txt",
        "title": "Attendance and Punctuality Policy",
        "category": "Attendance",
        "version": "1.1-file",
        "summary": (
            "Working attendance, punctuality, and absence "
            "notification rules."
        ),
        "content": """
WORKING SCHEDULE:
Employees must follow the work schedule assigned by their department.

LATE ARRIVAL:
An employee who expects to arrive late must notify the immediate manager
as soon as reasonably possible.

UNEXPECTED ABSENCE:
Employees must inform their manager and HR before the scheduled start time
when they cannot report for work.
""",
    },
)


def main() -> None:
    """Create missing sample uploaded policy versions."""

    initialize_runtime_schema()
    settings = get_settings()

    with SessionFactory() as session:
        company = CompanyRepository(session).get_by_code(
            settings.initial_company_code
        )

        if company is None:
            raise RuntimeError(
                "Configured company was not found. "
                "Run: python scripts/create_initial_data.py"
            )

        admin = UserRepository(session).get_by_username(
            company.id,
            settings.initial_admin_username,
        )

        if admin is None:
            raise RuntimeError(
                "Configured administrator was not found."
            )

        service = PolicyService(session)
        created_count = 0

        for item in SAMPLE_POLICIES:
            existing = service.repository.get_by_title_version(
                company_id=company.id,
                title=item["title"],
                version=item["version"],
            )

            if existing is not None:
                continue

            content_bytes = (
                item["content"].strip() + "\n"
            ).encode("utf-8")

            service.create_policy_from_upload(
                values=PolicyUploadRequest(
                    company_id=company.id,
                    created_by_user_id=admin.id,
                    title=item["title"],
                    category=item["category"],
                    summary=item["summary"],
                    version=item["version"],
                ),
                filename=item["filename"],
                file_bytes=content_bytes,
                mime_type="text/plain",
                maximum_size_bytes=(
                    settings.policy_upload_max_mb
                    * 1024
                    * 1024
                ),
            )

            created_count += 1

        print("Sample file-based policy setup completed.")
        print(f"Created policies: {created_count}")
        print("Existing policy versions were preserved.")


if __name__ == "__main__":
    main()
