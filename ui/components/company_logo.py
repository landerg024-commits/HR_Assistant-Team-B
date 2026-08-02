"""Company-scoped logo displayed at the top of protected sidebars."""

import base64
import html

import streamlit as st

from authentication.current_user import AuthenticatedUser
from database.session import SessionFactory
from services.organization_service import OrganizationService


def _load_company_logo(
    company_id: int,
) -> bytes | None:
    """Load a private logo without exposing its filesystem path."""

    try:
        with SessionFactory() as session:
            return OrganizationService(
                session
            ).get_company_logo_bytes(
                company_id
            )
    except Exception:
        # Sidebar navigation remains available when branding cannot load.
        return None


def render_company_sidebar_logo(
    current_user: AuthenticatedUser,
) -> None:
    """Render a centered, aspect-ratio-safe company logo or placeholder."""

    logo_bytes = _load_company_logo(
        current_user.company_id
    )

    if logo_bytes:
        encoded = base64.b64encode(
            logo_bytes
        ).decode("ascii")
        accessible_name = html.escape(
            f"{current_user.company_name} logo",
            quote=True,
        )
        content = (
            '<img src="data:image/png;base64,'
            f'{encoded}" alt="{accessible_name}">'
        )
    else:
        content = (
            '<div class="hr-sidebar-logo-placeholder">'
            '<span>Company Logo</span>'
            '</div>'
        )

    st.sidebar.markdown(
        (
            '<div class="hr-sidebar-logo-shell">'
            f'{content}'
            '</div>'
        ),
        unsafe_allow_html=True,
    )
