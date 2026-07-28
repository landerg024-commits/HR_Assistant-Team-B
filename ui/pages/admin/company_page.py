"""Administrator company-profile and branding page.

The company code remains the stable tenant key. Administrators may update
the display name and one company-wide accent color used by both portals.
"""

import streamlit as st
from pydantic import ValidationError

from authentication.current_user import AuthenticatedUser
from core.constants import DEFAULT_COMPANY_THEME_COLOR
from database.session import SessionFactory
from schemas.organization_schema import (
    CompanyNameUpdate,
    CompanyThemeColorUpdate,
)
from services.organization_service import OrganizationService
from ui.components.operation_feedback import (
    render_operation_feedback,
    set_operation_feedback,
)
from ui.theme.color_palette import build_accent_palette


def _theme_picker_key(
    company_id: int,
) -> str:
    """Return a reset-safe company color-picker key."""

    nonce_key = f"_company_theme_picker_nonce_{company_id}"
    nonce = int(st.session_state.get(nonce_key, 0))

    return f"company_theme_color_{company_id}_{nonce}"


def _advance_theme_picker(
    company_id: int,
) -> None:
    """Remount the picker after saving or resetting its value."""

    nonce_key = f"_company_theme_picker_nonce_{company_id}"
    st.session_state[nonce_key] = (
        int(st.session_state.get(nonce_key, 0))
        + 1
    )


def _render_theme_preview(
    selected_color: str,
) -> None:
    """Display the derived accessible accent states before saving."""

    palette = build_accent_palette(selected_color)

    st.markdown(
        f"""
        <div style="
            border:1px solid #D8DEEA;
            border-radius:14px;
            padding:16px;
            background:#FFFFFF;
            margin:8px 0 14px 0;
        ">
            <div style="
                color:#10172A;
                font-weight:700;
                margin-bottom:10px;
            ">
                Theme Preview
            </div>
            <div style="
                display:flex;
                flex-wrap:wrap;
                gap:10px;
                align-items:center;
            ">
                <div style="
                    min-width:170px;
                    padding:11px 15px;
                    border-radius:10px;
                    background:{palette["primary"]};
                    color:{palette["on_primary"]};
                    font-weight:700;
                    text-align:center;
                ">
                    Primary Action
                </div>
                <div style="
                    min-width:170px;
                    padding:11px 15px;
                    border-radius:10px;
                    background:{palette["primary_hover"]};
                    color:{palette["on_primary_hover"]};
                    font-weight:700;
                    text-align:center;
                ">
                    Hover State
                </div>
                <div style="
                    min-width:170px;
                    padding:11px 15px;
                    border-radius:10px;
                    background:{palette["primary_soft"]};
                    color:{palette["primary_text"]};
                    border:1px solid {palette["primary"]};
                    font-weight:700;
                    text-align:center;
                ">
                    Soft Accent
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_company_page(
    current_user: AuthenticatedUser,
) -> None:
    """Display and update company profile and branding."""

    st.title("Company Profile")
    st.caption(
        "Manage the company name and the accent color used throughout "
        "the Administration and Employee portals."
    )

    render_operation_feedback(namespace="company")

    with SessionFactory() as session:
        company = OrganizationService(session).get_company(
            current_user.company_id
        )

        company_code = company.code
        company_name = company.name
        company_theme_color = (
            company.theme_primary_color
            or DEFAULT_COMPANY_THEME_COLOR
        )
        company_status = (
            "Active" if company.is_active else "Inactive"
        )

    metric_columns = st.columns(4)

    with metric_columns[0]:
        st.metric("Company Code", company_code)

    with metric_columns[1]:
        st.metric("Status", company_status)

    with metric_columns[2]:
        st.metric("Tenant ID", current_user.company_id)

    with metric_columns[3]:
        st.metric("Theme Color", company_theme_color)

    st.subheader("Company Information")

    with st.form("company_profile_form"):
        st.text_input(
            "Company Code",
            value=company_code,
            disabled=True,
            help="Company code is the permanent tenant identifier.",
        )

        new_company_name = st.text_input(
            "Company Name",
            value=company_name,
            max_chars=200,
        )

        submitted = st.form_submit_button(
            "Save Company Information",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        try:
            request = CompanyNameUpdate(
                company_id=current_user.company_id,
                name=new_company_name,
            )

            with st.spinner("Saving company information…"):
                with SessionFactory() as session:
                    updated_company = OrganizationService(
                        session
                    ).update_company_name(request)

            session_user = current_user.to_session_dict()
            session_user["company_name"] = updated_company.name
            st.session_state.authenticated_user = session_user

            set_operation_feedback(
                "Company information updated successfully.",
                namespace="company",
            )
            st.rerun()

        except ValidationError as error:
            st.error(error.errors()[0]["msg"])
        except ValueError as error:
            st.error(str(error))
        except Exception:
            st.error("The company profile could not be updated.")

    st.subheader("Company Theme Color")
    st.caption(
        "Choose any primary color. The system automatically derives "
        "readable hover, soft-accent, and text colors."
    )

    picker_key = _theme_picker_key(current_user.company_id)
    selected_color = st.color_picker(
        "Primary Accent Color",
        value=company_theme_color,
        key=picker_key,
        help=(
            "Applied to active sidebar items, primary buttons, tabs, "
            "focus borders, badges, and hover accents."
        ),
    )

    _render_theme_preview(selected_color)

    save_column, reset_column = st.columns(2)

    with save_column:
        save_theme = st.button(
            "Save Theme Color",
            type="primary",
            use_container_width=True,
            key="save_company_theme_color",
        )

    with reset_column:
        reset_theme = st.button(
            "Reset to Default Violet",
            use_container_width=True,
            key="reset_company_theme_color",
        )

    if save_theme or reset_theme:
        target_color = (
            DEFAULT_COMPANY_THEME_COLOR
            if reset_theme
            else selected_color
        )

        try:
            request = CompanyThemeColorUpdate(
                company_id=current_user.company_id,
                primary_color=target_color,
            )

            with st.spinner("Applying company theme…"):
                with SessionFactory() as session:
                    updated_company = OrganizationService(
                        session
                    ).update_company_theme_color(request)

            _advance_theme_picker(current_user.company_id)
            set_operation_feedback(
                "Company theme reset to default violet."
                if reset_theme
                else (
                    "Company theme color updated to "
                    f"{updated_company.theme_primary_color}."
                ),
                namespace="company",
            )
            st.rerun()

        except ValidationError as error:
            st.error(error.errors()[0]["msg"])
        except ValueError as error:
            st.error(str(error))
        except Exception:
            st.error("The company theme could not be updated.")
