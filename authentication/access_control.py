"""Central clearance-based authorization rules."""

from authentication.current_user import AuthenticatedUser
from core.constants import CLEARANCE_ADMIN, CLEARANCE_USER


class AccessControl:
    """Reusable authorization checks using simple numeric clearance."""

    @staticmethod
    def is_admin(user: AuthenticatedUser) -> bool:
        """Return True only for clearance 1."""

        return user.clearance == CLEARANCE_ADMIN

    @staticmethod
    def is_manager(user: AuthenticatedUser) -> bool:
        """Compatibility rule: only administrators manage records."""

        return AccessControl.is_admin(user)

    @staticmethod
    def can_access_employee_portal(
        user: AuthenticatedUser,
    ) -> bool:
        """Both Admin and User accounts may open the employee portal."""

        return user.clearance in {
            CLEARANCE_ADMIN,
            CLEARANCE_USER,
        }

    @staticmethod
    def require_admin(user: AuthenticatedUser) -> None:
        """Stop clearance-2 users from opening admin layouts."""

        if not AccessControl.is_admin(user):
            raise PermissionError(
                "Administrator clearance is required."
            )
