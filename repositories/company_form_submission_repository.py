"""Employee company-form submission queries."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from models.company_form_submission import CompanyFormSubmission
from repositories.base_repository import BaseRepository


class CompanyFormSubmissionRepository(BaseRepository[CompanyFormSubmission]):
    """Tenant-safe persistence for completed employee forms."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, CompanyFormSubmission)

    def list_for_admin(self, company_id: int) -> list[CompanyFormSubmission]:
        statement = (
            select(CompanyFormSubmission)
            .options(
                joinedload(CompanyFormSubmission.form),
                joinedload(CompanyFormSubmission.employee),
            )
            .where(CompanyFormSubmission.company_id == company_id)
            .order_by(
                CompanyFormSubmission.created_at.desc(),
                CompanyFormSubmission.id.desc(),
            )
        )
        return list(self.session.scalars(statement).unique().all())

    def list_for_employee(
        self,
        *,
        company_id: int,
        employee_id: int,
    ) -> list[CompanyFormSubmission]:
        statement = (
            select(CompanyFormSubmission)
            .options(joinedload(CompanyFormSubmission.form))
            .where(
                CompanyFormSubmission.company_id == company_id,
                CompanyFormSubmission.employee_id == employee_id,
            )
            .order_by(
                CompanyFormSubmission.created_at.desc(),
                CompanyFormSubmission.id.desc(),
            )
        )
        return list(self.session.scalars(statement).unique().all())

    def count_all(self, company_id: int) -> int:
        return int(
            self.session.scalar(
                select(func.count(CompanyFormSubmission.id)).where(
                    CompanyFormSubmission.company_id == company_id
                )
            )
            or 0
        )

    def count_pending(self, company_id: int) -> int:
        return int(
            self.session.scalar(
                select(func.count(CompanyFormSubmission.id)).where(
                    CompanyFormSubmission.company_id == company_id,
                    CompanyFormSubmission.status == "submitted",
                )
            )
            or 0
        )
