"""Browser-cookie adapter for persistent login.

The third-party component is isolated in this module so the rest of the
authentication system does not depend directly on its API.
"""

from datetime import datetime

from config.settings import get_settings

try:
    from streamlit_cookies_controller import CookieController
except ImportError:  # pragma: no cover - user receives a clear runtime error.
    CookieController = None


COOKIE_NAME = "ai_hr_auth_session"
CONTROLLER_KEY = "ai_hr_cookie_controller"


class BrowserSessionCookie:
    """Read, write, and remove the persistent session cookie."""

    def __init__(self) -> None:
        if CookieController is None:
            raise RuntimeError(
                "streamlit-cookies-controller is not installed. "
                "Run: python -m pip install -r requirements.txt"
            )

        self.settings = get_settings()
        self.controller = CookieController(
            key=CONTROLLER_KEY
        )

    def get_token(self) -> str | None:
        """Return the current raw session token from the browser."""

        value = self.controller.get(COOKIE_NAME)

        if value is None:
            return None

        return str(value)

    def set_token(
        self,
        *,
        raw_token: str,
        expires_at: datetime,
    ) -> None:
        """Write a strict SameSite cookie for the login session."""

        self.controller.set(
            COOKIE_NAME,
            raw_token,
            path="/",
            expires=expires_at,
            secure=self.settings.auth_cookie_secure,
            same_site="strict",
        )

    def remove_token(self) -> None:
        """Remove the browser cookie when logging out or invalid."""

        # CookieController.remove() expects the cookie to exist.
        if self.controller.get(COOKIE_NAME) is None:
            return

        self.controller.remove(
            COOKIE_NAME,
            path="/",
            secure=self.settings.auth_cookie_secure,
            same_site="strict",
        )
