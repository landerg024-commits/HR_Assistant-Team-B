"""Stored source-file metadata for one company HR policy.

The original uploaded file remains private. ``storage_path`` is a relative
path under the configured policy upload directory and must never be treated
as a public URL.
"""

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin


class HRPolicyDocument(TimestampMixin, Base):
    """One original uploaded file attached to one policy version."""

    __tablename__ = "hr_policy_documents"

    __table_args__ = (
        UniqueConstraint(
            "policy_id",
            name="uq_hr_policy_documents_policy_id",
        ),
        UniqueConstraint(
            "company_id",
            "sha256",
            name="uq_hr_policy_documents_company_sha256",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    policy_id: Mapped[int] = mapped_column(
        ForeignKey("hr_policies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    uploaded_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )

    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    stored_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    storage_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    mime_type: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    file_extension: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    sha256: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
    )

    size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    page_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    extracted_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
