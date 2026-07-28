"""Shared layout for login and mandatory password change."""

from authentication.current_user import AuthenticatedUser
from config.settings import Settings
from ui.components.auth_sidebar import render_auth_sidebar
from ui.pages.authentication.change_password_page import (
    render_change_password_page,
)
from ui.pages.authentication.login_page import render_login_page
from ui.pages.authentication.forgot_password_page import (
    render_forgot_password_page,
)
from ui.pages.authentication.reset_password_page import (
    render_reset_password_page,
)


def render_login_layout(settings: Settings) -> None:
    """Render branding plus the login form."""

    render_auth_sidebar(
        assistant_name=settings.assistant_name,
        company_name=settings.company_name,
    )
    render_login_page(
        default_company_code=settings.initial_company_code
    )


def render_password_change_layout(
    settings: Settings,
    current_user: AuthenticatedUser,
) -> None:
    """Render branding plus mandatory password replacement."""

    render_auth_sidebar(
        assistant_name=settings.assistant_name,
        company_name=current_user.company_name,
    )
    render_change_password_page(current_user)



def render_forgot_password_layout(
    settings: Settings,
) -> None:
    """Render branding and the public reset-request page."""

    render_auth_sidebar(
        assistant_name=settings.assistant_name,
        company_name=settings.company_name,
    )
    render_forgot_password_page()


def render_reset_password_layout(
    settings: Settings,
) -> None:
    """Render branding and the public new-password page."""

    render_auth_sidebar(
        assistant_name=settings.assistant_name,
        company_name=settings.company_name,
    )
    render_reset_password_page()
