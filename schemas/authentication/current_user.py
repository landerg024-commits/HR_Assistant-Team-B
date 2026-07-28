"""Authenticated-user data transferred safely between layers.

Purpose:
- Keep the UI independent from live SQLAlchemy model objects.
- Store only identity, company, role, and employee display information.
- Avoid detached-model errors after a database session is closed.

Debugging:
If the UI shows incorrect user information, inspect from_model().
"""

from dataclasses import asdict, dataclass

from models.user import User


@dataclass(slots=True)
class AuthenticatedUser:
    """Safe user information stored in Streamlit session state."""

    user_id: int
    company_id: int
    company_code: str
    company_name: str
    role_id: int
    role_name: str
    username: str
    email: str
    employee_id: int | None
    employee_number: str | None
    employee_name: str | None
    must_change_password: bool

    @classmethod
    def from_model(cls, user: User) -> "AuthenticatedUser":
        """Create a session-safe value object from a loaded User model."""

        employee = user.employee

        return cls(
            user_id=user.id,
            company_id=user.company_id,
            company_code=user.company.code,
            company_name=user.company.name,
            role_id=user.role_id,
            role_name=user.role.name,
            username=user.username,
            email=user.email,
            employee_id=employee.id if employee else None,
            employee_number=(
                employee.employee_number if employee else None
            ),
            employee_name=(
                employee.full_name if employee else None
            ),
            must_change_password=user.must_change_password,
        )

    def to_session_dict(self) -> dict[str, object]:
        """Convert the dataclass into serializable session data."""

        return asdict(self)

    @classmethod
    def from_session_dict(
        cls,
        values: dict[str, object],
    ) -> "AuthenticatedUser":
        """Restore a typed user object from Streamlit session data."""

        return cls(**values)
