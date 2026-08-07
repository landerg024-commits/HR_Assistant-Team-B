"""Business rules for company forms and employee submissions."""

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import mimetypes
from uuid import uuid4

from sqlalchemy.orm import Session

from models.company_form import CompanyForm
from models.company_form_submission import CompanyFormSubmission
from modules.documents.company_form_file_storage import CompanyFormFileStorage
from repositories.company_form_repository import CompanyFormRepository
from repositories.company_form_submission_repository import (
    CompanyFormSubmissionRepository,
)
from repositories.user_repository import UserRepository
from services.notification_service import NotificationService


ALLOWED_FORM_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".csv",
    ".txt",
}

ALLOWED_SUBMISSION_EXTENSIONS = {
    *ALLOWED_FORM_EXTENSIONS,
    ".png",
    ".jpg",
    ".jpeg",
}

FORM_STATUSES = {"active", "trashed"}
SUBMISSION_STATUSES = {"submitted", "reviewed", "approved", "returned"}


@dataclass(slots=True)
class CompanyFormDownload:
    """Authorized file bytes used by Streamlit download buttons."""

    filename: str
    mime_type: str
    data: bytes


@dataclass(slots=True)
class CompanyFormOverview:
    """Small dashboard summary for the administrator Overview tab."""

    active_forms: int
    total_submissions: int
    pending_submissions: int
    bin_forms: int


class CompanyFormService:
    """Manage company templates and employee-completed form submissions."""

    def __init__(
        self,
        session: Session,
        *,
        storage: CompanyFormFileStorage | None = None,
    ) -> None:
        self.session = session
        self.forms = CompanyFormRepository(session)
        self.submissions = CompanyFormSubmissionRepository(session)
        self.users = UserRepository(session)
        self.notifications = NotificationService(session)
        self.storage = storage or CompanyFormFileStorage()

    @staticmethod
    def _clean_text(value: str | None, *, maximum: int) -> str:
        return " ".join((value or "").split())[:maximum]

    @staticmethod
    def _safe_filename(filename: str | None) -> str:
        cleaned = Path(filename or "").name.strip()
        if not cleaned:
            raise ValueError("Select a valid file.")
        return cleaned[:255]

    @staticmethod
    def _validate_file(
        *,
        filename: str,
        file_bytes: bytes,
        allowed_extensions: set[str],
        maximum_size_bytes: int,
    ) -> tuple[str, str, str, int]:
        safe_name = CompanyFormService._safe_filename(filename)
        extension = Path(safe_name).suffix.lower()

        if extension not in allowed_extensions:
            readable = ", ".join(sorted(allowed_extensions))
            raise ValueError(f"Unsupported file type. Allowed: {readable}.")

        size_bytes = len(file_bytes)
        if size_bytes <= 0:
            raise ValueError("The selected file is empty.")
        if size_bytes > maximum_size_bytes:
            raise ValueError(
                "The selected file exceeds the configured upload limit."
            )

        mime_type = (
            mimetypes.guess_type(safe_name)[0]
            or "application/octet-stream"
        )
        digest = sha256(file_bytes).hexdigest()
        return extension, mime_type, digest, size_bytes

    @staticmethod
    def form_public_id(form_id: int) -> str:
        return f"FORM_{form_id:06d}"

    @staticmethod
    def submission_public_id(submission_id: int) -> str:
        return f"FSUB_{submission_id:06d}"

    def overview(self, company_id: int) -> CompanyFormOverview:
        return CompanyFormOverview(
            active_forms=self.forms.active_count(company_id),
            total_submissions=self.submissions.count_all(company_id),
            pending_submissions=self.submissions.count_pending(company_id),
            bin_forms=len(self.forms.list_bin(company_id)),
        )

    def list_active_forms(self, company_id: int) -> list[CompanyForm]:
        return self.forms.list_active(company_id)

    def list_bin_forms(self, company_id: int) -> list[CompanyForm]:
        return self.forms.list_bin(company_id)

    def list_admin_submissions(
        self,
        company_id: int,
    ) -> list[CompanyFormSubmission]:
        return self.submissions.list_for_admin(company_id)

    def list_employee_submissions(
        self,
        *,
        company_id: int,
        employee_id: int,
    ) -> list[CompanyFormSubmission]:
        return self.submissions.list_for_employee(
            company_id=company_id,
            employee_id=employee_id,
        )

    def upload_form(
        self,
        *,
        company_id: int,
        uploaded_by_user_id: int,
        title: str,
        category: str,
        description: str,
        allow_employee_submission: bool,
        filename: str,
        file_bytes: bytes,
        maximum_size_bytes: int,
    ) -> CompanyForm:
        normalized_title = self._clean_text(title, maximum=180)
        normalized_category = self._clean_text(category, maximum=100)
        normalized_description = (description or "").strip()[:4000]

        if len(normalized_title) < 2:
            raise ValueError("Enter a complete form title.")
        if not normalized_category:
            raise ValueError("Enter or select a form category.")

        extension, mime_type, digest, size_bytes = self._validate_file(
            filename=filename,
            file_bytes=file_bytes,
            allowed_extensions=ALLOWED_FORM_EXTENSIONS,
            maximum_size_bytes=maximum_size_bytes,
        )

        if self.forms.duplicate_hash(
            company_id=company_id,
            sha256=digest,
        ) is not None:
            raise ValueError(
                "This exact form file is already active for the company."
            )

        stored = self.storage.save_template(
            company_id=company_id,
            original_filename=filename,
            file_bytes=file_bytes,
        )

        try:
            form = CompanyForm(
                public_id=f"TEMP_{uuid4().hex}",
                company_id=company_id,
                uploaded_by_user_id=uploaded_by_user_id,
                title=normalized_title,
                category=normalized_category,
                description=normalized_description,
                allow_employee_submission=allow_employee_submission,
                status="active",
                original_filename=self._safe_filename(filename),
                stored_filename=stored.stored_filename,
                storage_path=stored.relative_path,
                mime_type=mime_type,
                file_extension=extension,
                sha256=digest,
                size_bytes=size_bytes,
            )
            self.session.add(form)
            self.session.flush()
            form.public_id = self.form_public_id(form.id)

            # Employees receive one bell notification for a newly available form.
            for user_id in self.users.list_active_ids(
                company_id=company_id,
                exclude_user_id=uploaded_by_user_id,
            ):
                self.notifications.create(
                    company_id=company_id,
                    user_id=user_id,
                    event_type="company_form_published",
                    title=f"New company form: {form.title}",
                    message=(
                        "Open Company Form/Documents to view or download the "
                        "new form."
                    ),
                    related_entity_type="company_form",
                    related_entity_id=form.id,
                )

            self.session.commit()
            self.session.refresh(form)
            return form
        except Exception:
            self.session.rollback()
            self.storage.delete(stored.relative_path)
            raise

    def update_form_metadata(
        self,
        *,
        company_id: int,
        form_id: int,
        title: str,
        category: str,
        description: str,
        allow_employee_submission: bool,
    ) -> CompanyForm:
        form = self.forms.get_by_id(form_id, company_id)
        if form is None or form.status != "active":
            raise ValueError("The selected active form was not found.")

        normalized_title = self._clean_text(title, maximum=180)
        normalized_category = self._clean_text(category, maximum=100)
        if len(normalized_title) < 2:
            raise ValueError("Enter a complete form title.")
        if not normalized_category:
            raise ValueError("Enter a form category.")

        form.title = normalized_title
        form.category = normalized_category
        form.description = (description or "").strip()[:4000]
        form.allow_employee_submission = allow_employee_submission
        self.session.commit()
        self.session.refresh(form)
        return form

    def move_to_bin(
        self,
        *,
        company_id: int,
        form_id: int,
        user_id: int,
    ) -> CompanyForm:
        form = self.forms.get_by_id(form_id, company_id)
        if form is None or form.status != "active":
            raise ValueError("The selected active form was not found.")

        form.status = "trashed"
        form.trashed_at = datetime.now(timezone.utc)
        form.trashed_by_user_id = user_id
        self.session.commit()
        self.session.refresh(form)
        return form

    def restore_from_bin(
        self,
        *,
        company_id: int,
        form_id: int,
    ) -> CompanyForm:
        form = self.forms.get_by_id(form_id, company_id)
        if form is None or form.status != "trashed":
            raise ValueError("The selected Bin form was not found.")

        form.status = "active"
        form.trashed_at = None
        form.trashed_by_user_id = None
        self.session.commit()
        self.session.refresh(form)
        return form

    def permanently_delete(
        self,
        *,
        company_id: int,
        form_id: int,
    ) -> None:
        form = self.forms.get_by_id(form_id, company_id)
        if form is None or form.status != "trashed":
            raise ValueError("Move the form to Bin before permanent deletion.")

        template_path = form.storage_path
        submission_paths = [item.storage_path for item in form.submissions]
        self.session.delete(form)
        self.session.commit()
        self.storage.delete(template_path)
        for path in submission_paths:
            self.storage.delete(path)

    def get_form_download(
        self,
        *,
        company_id: int,
        form_id: int,
        active_only: bool = True,
    ) -> CompanyFormDownload:
        form = self.forms.get_by_id(form_id, company_id)
        if form is None or (active_only and form.status != "active"):
            raise ValueError("The selected company form was not found.")
        return CompanyFormDownload(
            filename=form.original_filename,
            mime_type=form.mime_type,
            data=self.storage.read(form.storage_path),
        )

    def submit_completed_form(
        self,
        *,
        company_id: int,
        form_id: int,
        employee_id: int,
        submitted_by_user_id: int,
        notes: str,
        filename: str,
        file_bytes: bytes,
        maximum_size_bytes: int,
    ) -> CompanyFormSubmission:
        form = self.forms.get_by_id(form_id, company_id)
        if form is None or form.status != "active":
            raise ValueError("The selected company form is no longer available.")
        if not form.allow_employee_submission:
            raise ValueError(
                "This company document is download-only and does not accept submissions."
            )

        extension, mime_type, digest, size_bytes = self._validate_file(
            filename=filename,
            file_bytes=file_bytes,
            allowed_extensions=ALLOWED_SUBMISSION_EXTENSIONS,
            maximum_size_bytes=maximum_size_bytes,
        )
        stored = self.storage.save_submission(
            company_id=company_id,
            employee_id=employee_id,
            original_filename=filename,
            file_bytes=file_bytes,
        )

        try:
            submission = CompanyFormSubmission(
                public_id=f"TEMP_{uuid4().hex}",
                company_id=company_id,
                form_id=form.id,
                employee_id=employee_id,
                submitted_by_user_id=submitted_by_user_id,
                notes=(notes or "").strip()[:4000],
                status="submitted",
                admin_note="",
                original_filename=self._safe_filename(filename),
                stored_filename=stored.stored_filename,
                storage_path=stored.relative_path,
                mime_type=mime_type,
                file_extension=extension,
                sha256=digest,
                size_bytes=size_bytes,
            )
            self.session.add(submission)
            self.session.flush()
            submission.public_id = self.submission_public_id(submission.id)

            for admin_id in self.users.list_active_admin_ids(company_id=company_id):
                self.notifications.create(
                    company_id=company_id,
                    user_id=admin_id,
                    event_type="company_form_submitted",
                    title=f"Completed form submitted: {form.title}",
                    message=(
                        "An employee submitted a completed company form. "
                        "Open Company Form/Documents > Overview to review it."
                    ),
                    related_entity_type="company_form_submission",
                    related_entity_id=submission.id,
                )

            self.session.commit()
            self.session.refresh(submission)
            return submission
        except Exception:
            self.session.rollback()
            self.storage.delete(stored.relative_path)
            raise

    def get_submission_download(
        self,
        *,
        company_id: int,
        submission_id: int,
        employee_id: int | None = None,
    ) -> CompanyFormDownload:
        submission = self.submissions.get_by_id(submission_id, company_id)
        if submission is None:
            raise ValueError("The selected employee submission was not found.")
        if employee_id is not None and submission.employee_id != employee_id:
            raise ValueError("You cannot access another employee's submission.")
        return CompanyFormDownload(
            filename=submission.original_filename,
            mime_type=submission.mime_type,
            data=self.storage.read(submission.storage_path),
        )

    def update_submission_status(
        self,
        *,
        company_id: int,
        submission_id: int,
        reviewed_by_user_id: int,
        status: str,
        admin_note: str,
    ) -> CompanyFormSubmission:
        normalized_status = status.strip().lower()
        if normalized_status not in SUBMISSION_STATUSES:
            raise ValueError("Select a valid submission status.")

        submission = self.submissions.get_by_id(submission_id, company_id)
        if submission is None:
            raise ValueError("The selected employee submission was not found.")

        submission.status = normalized_status
        submission.admin_note = (admin_note or "").strip()[:4000]
        submission.reviewed_by_user_id = reviewed_by_user_id
        submission.reviewed_at = datetime.now(timezone.utc)

        self.notifications.create(
            company_id=company_id,
            user_id=submission.submitted_by_user_id,
            event_type="company_form_status_updated",
            title=f"Form submission {normalized_status.title()}",
            message=(
                f"Your {submission.public_id} submission status is now "
                f"{normalized_status.title()}."
            ),
            related_entity_type="company_form_submission",
            related_entity_id=submission.id,
        )

        self.session.commit()
        self.session.refresh(submission)
        return submission
