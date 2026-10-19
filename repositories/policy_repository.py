"""Company-scoped HR policy database queries."""

from datetime import date, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from models.hr_policy import HRPolicy
from repositories.base_repository import BaseRepository


class PolicyRepository(BaseRepository[HRPolicy]):
    """Repository for active, versioned, and Bin policy records."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, HRPolicy)

    def get_by_title_version(self, *, company_id: int, title: str, version: str) -> HRPolicy | None:
        return self.session.scalar(
            select(HRPolicy).where(
                HRPolicy.company_id == company_id,
                HRPolicy.title == title,
                HRPolicy.version == version,
            )
        )

    def list_for_admin(self, company_id: int) -> list[HRPolicy]:
        """Return all versions that are not in the Bin."""
        return list(self.session.scalars(
            select(HRPolicy).where(
                HRPolicy.company_id == company_id,
                HRPolicy.status != "trashed",
            ).order_by(HRPolicy.created_at.desc(), HRPolicy.title, HRPolicy.version)
        ).all())

    def list_bin(self, company_id: int) -> list[HRPolicy]:
        """Return retained versions currently stored in the Bin."""
        return list(self.session.scalars(
            select(HRPolicy).where(
                HRPolicy.company_id == company_id,
                HRPolicy.status == "trashed",
            ).order_by(HRPolicy.trashed_at.desc(), HRPolicy.created_at.desc())
        ).all())

    def list_all_versions(self, company_id: int) -> list[HRPolicy]:
        return list(self.session.scalars(
            select(HRPolicy).where(HRPolicy.company_id == company_id)
            .order_by(HRPolicy.title, HRPolicy.created_at.desc())
        ).all())

    def list_by_title(self, *, company_id: int, title: str) -> list[HRPolicy]:
        return list(self.session.scalars(
            select(HRPolicy).where(
                HRPolicy.company_id == company_id,
                HRPolicy.title == title,
            ).order_by(HRPolicy.created_at.desc(), HRPolicy.id.desc())
        ).all())

    def list_published(self, *, company_id: int, as_of_date: date) -> list[HRPolicy]:
        statement = select(HRPolicy).where(
            HRPolicy.company_id == company_id,
            HRPolicy.status == "published",
            or_(HRPolicy.effective_date.is_(None), HRPolicy.effective_date <= as_of_date),
        ).order_by(HRPolicy.category, HRPolicy.title, HRPolicy.created_at.desc())
        return list(self.session.scalars(statement).all())

    def update_status(self, *, company_id: int, policy_id: int, status: str, published_at) -> HRPolicy | None:
        policy = self.get_by_id(record_id=policy_id, company_id=company_id)
        if policy is None: return None
        policy.status = status
        policy.published_at = published_at
        self.session.commit(); self.session.refresh(policy)
        return policy

    def move_to_bin(self, *, company_id: int, policy_id: int, user_id: int, moved_at: datetime) -> HRPolicy | None:
        policy = self.get_by_id(record_id=policy_id, company_id=company_id)
        if policy is None: return None
        policy.status = "trashed"
        policy.trashed_at = moved_at
        policy.trashed_by_user_id = user_id
        self.session.commit(); self.session.refresh(policy)
        return policy

    def restore_from_bin(self, *, company_id: int, policy_id: int, restored_at: datetime) -> HRPolicy | None:
        policy = self.get_by_id(record_id=policy_id, company_id=company_id)
        if policy is None: return None
        policy.status = "published"
        policy.published_at = policy.published_at or restored_at
        policy.trashed_at = None
        policy.trashed_by_user_id = None
        self.session.commit(); self.session.refresh(policy)
        return policy
