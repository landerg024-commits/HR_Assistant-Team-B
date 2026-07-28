"""User-specific database queries.

Authentication queries eagerly load company, role, and employee relations.
This allows AuthService to build session-safe values before closing a
database session.
"""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from models.user import User
from repositories.base_repository import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for company-scoped login accounts."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, User)

    def get_by_username(
        self,
        company_id: int,
        username: str,
    ) -> User | None:
        """Find a username inside one company."""

        return self.session.scalar(
            select(User).where(
                User.company_id == company_id,
                User.username == username,
            )
        )

    def get_by_email(
        self,
        company_id: int,
        email: str,
    ) -> User | None:
        """Find an email inside one company."""

        return self.session.scalar(
            select(User).where(
                User.company_id == company_id,
                User.email == email,
            )
        )

    def get_for_authentication(
        self,
        company_id: int,
        login_identifier: str,
    ) -> User | None:
        """Load by username or email with required relationships."""

        statement = (
            select(User)
            .options(
                joinedload(User.company),
                joinedload(User.role),
                joinedload(User.employee),
            )
            .where(
                User.company_id == company_id,
                or_(
                    User.username == login_identifier,
                    User.email == login_identifier,
                ),
            )
        )

        return self.session.scalar(statement)

    def get_for_password_change(
        self,
        company_id: int,
        user_id: int,
    ) -> User | None:
        """Load one account and relations for password replacement."""

        statement = (
            select(User)
            .options(
                joinedload(User.company),
                joinedload(User.role),
                joinedload(User.employee),
            )
            .where(
                User.company_id == company_id,
                User.id == user_id,
            )
        )

        return self.session.scalar(statement)
