"""Company-scoped login page."""

import streamlit as st

from authentication.access_control import AccessControl
from pydantic import ValidationError

from authentication.auth_service import (
    AuthenticationError,
    AuthService,
)
from authentication.session_manager import AuthSessionManager
from authentication.signed_cookie_auth_service import SignedCookieAuthService
from database.session import SessionFactory
from schemas.auth_schema import LoginRequest
from ui.auth_navigation import (
    PUBLIC_COMPANY_KEY,
    open_forgot_password,
)


def render_login_page(default_company_code: str) -> None:
    """Render and process the login form."""

    st.title("Welcome Back")
    st.caption(
        "Sign in to access HR services and administration tools."
    )

    if st.session_state.pop(
        "password_reset_success",
        False,
    ):
        st.success(
            "Your password was reset successfully. "
            "Sign in using the new password."
        )

    _, center, _ = st.columns([1, 1.4, 1])

    with center:
        st.markdown(
            """
            <div class="hr-card">
                <div class="hr-card-title">Account Login</div>
                <div class="hr-card-text">
                    Enter your company code, username or email, and password.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Keep all credentials in one form. A Company Code widget with an
        # on_change callback outside the form can rerun Streamlit before the
        # submit event is processed, which makes the first click appear to fail.
        with st.form(
            "login_form",
            clear_on_submit=False,
        ):
            company_code = st.text_input(
                "Company Code",
                value=default_company_code,
                max_chars=50,
                key="login_company_code",
                help=(
                    "Enter the company code assigned by your administrator."
                ),
            )
            login_identifier = st.text_input(
                "Username or Email",
                max_chars=255,
                key="login_identifier",
            )
            password = st.text_input(
                "Password",
                type="password",
                max_chars=128,
                key="login_password",
            )

            submitted = st.form_submit_button(
                "Sign In",
                use_container_width=True,
                type="primary",
            )

        if st.button(
            "Forgot Password?",
            use_container_width=True,
            key="open_forgot_password",
        ):
            open_forgot_password()

        if submitted:
            try:
                normalized_company_code = company_code.strip().upper()
                st.session_state["public_company_code"] = (
                    normalized_company_code
                )

                request = LoginRequest(
                    company_code=company_code,
                    login_identifier=login_identifier,
                    password=password,
                )

                with SessionFactory() as session:
                    current_user = AuthService(
                        session
                    ).authenticate(
                        company_code=request.company_code,
                        login_identifier=request.login_identifier,
                        password=request.password,
                    )

                    signed_token = SignedCookieAuthService(
                        session
                    ).issue_token(current_user)

                # Do not update query parameters or start a Streamlit rerun
                # before the browser has committed the signed cookie.
                if AccessControl.is_admin(current_user):
                    st.session_state.portal_mode = "admin"
                    st.session_state.current_page = "Admin Dashboard"
                else:
                    st.session_state.portal_mode = "employee"
                    st.session_state.current_page = "Dashboard"

                AuthSessionManager.complete_login(
                    current_user,
                    signed_token=signed_token,
                )

            except ValidationError as error:
                st.error(error.errors()[0]["msg"])
            except AuthenticationError as error:
                st.error(str(error))
            except Exception:
                # Do not reveal database or internal exception details.
                st.error(
                    "Login could not be completed. "
                    "Please contact your administrator."
                )
