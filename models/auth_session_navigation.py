"""Persistent page and portal state for one login session.

A separate table avoids altering the existing ``auth_sessions`` table.
Existing SQLite and PostgreSQL databases can therefore add this feature
through ``Base.metadata.create_all()`` without deleting current data.
"""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from models.auth_session import AuthSession


class AuthSessionNavigation(TimestampMixin, Base):
    """Last valid portal and page for one browser login session."""

    __tablename__ = "auth_session_navigation"

    id: Mapped[int] = mapped_column(primary_key=True)

    auth_session_id: Mapped[int] = mapped_column(
        ForeignKey("auth_sessions.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )

    portal_mode: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="employee",
    )

    current_page: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="Chat Assistant",
    )

    auth_session: Mapped["AuthSession"] = relationship()
