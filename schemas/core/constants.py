"""Shared application constants."""

SUPPORTED_THEMES = ("light", "dark")
DEFAULT_PAGE = "Chat Assistant"

SYSTEM_ROLES = (
    "super_admin",
    "company_admin",
    "hr_admin",
    "manager",
    "employee",
)

SYSTEM_ROLE_DESCRIPTIONS = {
    "super_admin": "Platform-level administrator.",
    "company_admin": "Administrator for one company.",
    "hr_admin": "Human Resources administrator.",
    "manager": "Employee manager and approver.",
    "employee": "Standard employee account.",
}

USER_NAVIGATION = (
    "Chat Assistant",
    "Dashboard",
    "My Requests",
    "Leave Management",
    "My Documents",
    "Company Policies",
    "Benefits",
    "Onboarding",
    "HR Contacts",
    "FAQ",
)
