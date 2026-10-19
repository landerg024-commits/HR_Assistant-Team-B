"""User-account business logic."""

from sqlalchemy.orm import Session

from authentication.password_manager import PasswordManager
from repositories.user_repository import UserRepository
from schemas.user_schema import UserCreate


class UserService:
    """Create company-scoped login accounts securely."""

    def __init__(
        self,
        session: Session,
        password_manager: PasswordManager | None = None,
    ) -> None:
        self.repository = UserRepository(session)
        self.password_manager = (
            password_manager or PasswordManager()
        )

    def create_user(
        self,
        values: UserCreate,
        *,
        must_change_password: bool = True,
    ):
        """Create a user after validating uniqueness and hashing password."""

        if self.repository.get_by_username(
            values.company_id,
            values.username,
        ):
            raise ValueError(
                f"Username '{values.username}' already exists "
                "inside this company."
            )

        if self.repository.get_by_email(
            values.company_id,
            str(values.email),
        ):
            raise ValueError(
                f"Email '{values.email}' already exists "
                "inside this company."
            )

        # Remove plain password before creating the database payload.
        payload = values.model_dump(
            exclude={"password"}
        )
        payload["email"] = str(values.email)

        # Only the generated Argon2 hash is stored.
        payload["password_hash"] = (
            self.password_manager.hash_password(
                values.password
            )
        )
        payload["must_change_password"] = must_change_password

        return self.repository.create(payload)
