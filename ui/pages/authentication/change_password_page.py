"""Mandatory temporary-password replacement page."""

import streamlit as st
from pydantic import ValidationError

from authentication.auth_service import (
    AuthenticationError,
    AuthService,
)
from authentication.current_user import AuthenticatedUser
from authentication.session_manager import AuthSessionManager
from authentication.signed_cookie_auth_service import SignedCookieAuthService
from database.session import SessionFactory
from schemas.auth_schema import PasswordChangeRequest


def render_change_password_page(
    current_user: AuthenticatedUser,
) -> None:
    """Block protected pages until the password is replaced."""

    st.title("Change Your Password")
    st.warning(
        "You must change your temporary password before continuing."
    )

    _, center, _ = st.columns([1, 1.4, 1])

    with center:
        with st.form(
            "forced_password_change_form",
            clear_on_submit=True,
        ):
            current_password = st.text_input(
                "Current Password",
                type="password",
                max_chars=128,
            )
            new_password = st.text_input(
                "New Password",
                type="password",
                max_chars=128,
                help="Use at least 8 characters.",
            )
            confirm_password = st.text_input(
                "Confirm New Password",
                type="password",
                max_chars=128,
            )

            submitted = st.form_submit_button(
                "Update Password",
                use_container_width=True,
                type="primary",
            )

        if submitted:
            try:
                request = PasswordChangeRequest(
                    current_password=current_password,
                    new_password=new_password,
                    confirm_password=confirm_password,
                )

                with SessionFactory() as session:
                    updated_user = AuthService(
                        session
                    ).change_password(
                        company_id=current_user.company_id,
                        user_id=current_user.user_id,
                        current_password=request.current_password,
                        new_password=request.new_password,
                    )

                    # Password changes invalidate the old fingerprint, so a
                    # new signed cookie is issued immediately.
                    signed_token = SignedCookieAuthService(
                        session
                    ).issue_token(updated_user)

                AuthSessionManager.complete_password_change(
                    updated_user,
                    signed_token=signed_token,
                )

            except ValidationError as error:
                st.error(error.errors()[0]["msg"])
            except AuthenticationError as error:
                st.error(str(error))
            except Exception:
                st.error(
                    "The password could not be updated. "
                    "Please contact your administrator."
                )
