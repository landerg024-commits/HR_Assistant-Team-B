"""Searchable uploaded-policy section database queries."""

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from models.hr_policy import HRPolicy
from models.hr_policy_document import HRPolicyDocument
from models.hr_policy_section import HRPolicySection
from repositories.base_repository import BaseRepository


class PolicySectionRepository(
    BaseRepository[HRPolicySection]
):
    """Repository for extracted policy sections."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, HRPolicySection)

    def list_searchable(
        self,
        *,
        company_id: int,
        as_of_date: date,
    ) -> list[
        tuple[
            HRPolicy,
            HRPolicyDocument,
            HRPolicySection,
        ]
    ]:
        """Return published, effective sections for one company only."""

        statement = (
            select(
                HRPolicy,
                HRPolicyDocument,
                HRPolicySection,
            )
            .join(
                HRPolicyDocument,
                HRPolicyDocument.policy_id == HRPolicy.id,
            )
            .join(
                HRPolicySection,
                HRPolicySection.document_id
                == HRPolicyDocument.id,
            )
            .where(
                HRPolicy.company_id == company_id,
                HRPolicyDocument.company_id == company_id,
                HRPolicySection.company_id == company_id,
                HRPolicy.status == "published",
                or_(
                    HRPolicy.effective_date.is_(None),
                    HRPolicy.effective_date <= as_of_date,
                ),
            )
            .order_by(
                HRPolicy.id,
                HRPolicySection.sequence_number,
            )
        )

        return list(self.session.execute(statement).all())

    def list_for_document(
        self,
        *,
        company_id: int,
        document_id: int,
    ) -> list[HRPolicySection]:
        """Return ordered extracted sections for one document."""

        statement = (
            select(HRPolicySection)
            .where(
                HRPolicySection.company_id == company_id,
                HRPolicySection.document_id == document_id,
            )
            .order_by(
                HRPolicySection.sequence_number,
            )
        )

        return list(
            self.session.scalars(statement).all()
        )
