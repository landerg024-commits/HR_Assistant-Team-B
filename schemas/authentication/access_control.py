"""Central role-based access-control rules.

Keeping role checks here prevents UI pages from hardcoding permission logic.
"""

from authentication.current_user import AuthenticatedUser


ADMIN_ROLES = {
    "super_admin",
    "company_admin",
    "hr_admin",
}

MANAGER_ROLES = {
    *ADMIN_ROLES,
    "manager",
}

EMPLOYEE_ROLES = {
    *MANAGER_ROLES,
    "employee",
}


class AccessControl:
    """Reusable authorization checks."""

    @staticmethod
    def is_admin(user: AuthenticatedUser) -> bool:
        """Return True for administrator roles."""

        return user.role_name in ADMIN_ROLES

    @staticmethod
    def is_manager(user: AuthenticatedUser) -> bool:
        """Return True for manager and administrator roles."""

        return user.role_name in MANAGER_ROLES

    @staticmethod
    def can_access_employee_portal(
        user: AuthenticatedUser,
    ) -> bool:
        """Return True for every recognized active role."""

        return user.role_name in EMPLOYEE_ROLES

    @staticmethod
    def require_admin(user: AuthenticatedUser) -> None:
        """Stop non-admin users from opening admin layouts."""

        if not AccessControl.is_admin(user):
            raise PermissionError(
                "Administrator access is required."
            )
