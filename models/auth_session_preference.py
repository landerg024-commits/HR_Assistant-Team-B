"""Persistent visual preferences for one authenticated browser session.

Purpose:
- Remember the last selected light or dark theme.
- Keep preferences separate per browser/device login session.
- Avoid changing existing tables during this incremental upgrade.

The preference is not security-sensitive. Authentication validity still
comes exclusively from the persistent auth session.
"""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from models.auth_session import AuthSession


class AuthSessionPreference(TimestampMixin, Base):
    """Last visual preference for one persistent login session."""

    __tablename__ = "auth_session_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)

    auth_session_id: Mapped[int] = mapped_column(
        ForeignKey(
            "auth_sessions.id",
            ondelete="CASCADE",
        ),
        unique=True,
        index=True,
        nullable=False,
    )

    theme: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="light",
    )

    auth_session: Mapped["AuthSession"] = relationship()
