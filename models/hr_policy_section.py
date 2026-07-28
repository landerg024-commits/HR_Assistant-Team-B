"""Searchable sections extracted from uploaded policy files."""

from sqlalchemy import (
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin


class HRPolicySection(TimestampMixin, Base):
    """One ordered searchable section from an uploaded policy file."""

    __tablename__ = "hr_policy_sections"

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "sequence_number",
            name="uq_hr_policy_sections_document_sequence",
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

    document_id: Mapped[int] = mapped_column(
        ForeignKey(
            "hr_policy_documents.id",
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
    )

    sequence_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    heading: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
    )

    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    page_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
