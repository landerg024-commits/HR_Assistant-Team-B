"""Company-scoped database queries for uploaded policy files."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.hr_policy_document import HRPolicyDocument
from repositories.base_repository import BaseRepository


class PolicyDocumentRepository(
    BaseRepository[HRPolicyDocument]
):
    """Repository for private uploaded policy documents."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, HRPolicyDocument)

    def get_by_policy(
        self,
        *,
        company_id: int,
        policy_id: int,
    ) -> HRPolicyDocument | None:
        """Return the source file metadata for one company policy."""

        return self.session.scalar(
            select(HRPolicyDocument).where(
                HRPolicyDocument.company_id == company_id,
                HRPolicyDocument.policy_id == policy_id,
            )
        )

    def get_by_hash(
        self,
        *,
        company_id: int,
        sha256: str,
    ) -> HRPolicyDocument | None:
        """Return an exact duplicate file inside the same company."""

        return self.session.scalar(
            select(HRPolicyDocument).where(
                HRPolicyDocument.company_id == company_id,
                HRPolicyDocument.sha256 == sha256,
            )
        )

    def list_for_policies(
        self,
        *,
        company_id: int,
        policy_ids: list[int],
    ) -> list[HRPolicyDocument]:
        """Return source files for a group of company policies."""

        if not policy_ids:
            return []

        statement = select(HRPolicyDocument).where(
            HRPolicyDocument.company_id == company_id,
            HRPolicyDocument.policy_id.in_(policy_ids),
        )

        return list(
            self.session.scalars(statement).all()
        )
