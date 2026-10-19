"""Company form template queries."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.company_form import CompanyForm
from repositories.base_repository import BaseRepository


class CompanyFormRepository(BaseRepository[CompanyForm]):
    """Tenant-safe persistence for company form templates."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, CompanyForm)

    def list_active(self, company_id: int) -> list[CompanyForm]:
        statement = (
            select(CompanyForm)
            .where(
                CompanyForm.company_id == company_id,
                CompanyForm.status == "active",
            )
            .order_by(CompanyForm.updated_at.desc(), CompanyForm.id.desc())
        )
        return list(self.session.scalars(statement).all())

    def list_bin(self, company_id: int) -> list[CompanyForm]:
        statement = (
            select(CompanyForm)
            .where(
                CompanyForm.company_id == company_id,
                CompanyForm.status == "trashed",
            )
            .order_by(CompanyForm.trashed_at.desc(), CompanyForm.id.desc())
        )
        return list(self.session.scalars(statement).all())

    def duplicate_hash(self, *, company_id: int, sha256: str) -> CompanyForm | None:
        return self.session.scalar(
            select(CompanyForm).where(
                CompanyForm.company_id == company_id,
                CompanyForm.sha256 == sha256,
                CompanyForm.status == "active",
            )
        )

    def active_count(self, company_id: int) -> int:
        return int(
            self.session.scalar(
                select(func.count(CompanyForm.id)).where(
                    CompanyForm.company_id == company_id,
                    CompanyForm.status == "active",
                )
            )
            or 0
        )
