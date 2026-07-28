"""Signed refresh-safe authentication token service.

Design:
- No password or password hash is stored in the browser.
- The cookie contains a signed user/company identifier and a short
  fingerprint derived from the current Argon2 password hash.
- Any cookie modification invalidates its signature.
- Password changes invalidate old cookies because the fingerprint changes.
- Account, company, and role status are rechecked during restoration.
- No additional database table is required.

A configured AUTH_COOKIE_SECRET is recommended for production. When it is
not configured, a random process-only secret is generated. That still
preserves authentication across browser refreshes while the Streamlit
server remains running, but intentionally requires login after a server
restart.
"""

import hashlib
import secrets
from typing import Any

from itsdangerous import (
    BadSignature,
    SignatureExpired,
    URLSafeTimedSerializer,
)
from sqlalchemy.orm import Session

from authentication.current_user import AuthenticatedUser
from config.settings import get_settings
from repositories.user_repository import UserRepository


_PROCESS_COOKIE_SECRET = secrets.token_urlsafe(48)
_TOKEN_SALT = "ai-hr-assistant-auth-cookie-v1"
_TOKEN_VERSION = 1


class SignedCookieAuthenticationError(ValueError):
    """Raised when a signed authentication cookie is invalid."""


class SignedCookieAuthService:
    """Issue and restore signed browser authentication tokens."""

    def __init__(
        self,
        session: Session,
        *,
        max_age_seconds: int | None = None,
        secret_key: str | None = None,
    ) -> None:
        self.session = session
        self.user_repository = UserRepository(session)

        settings = get_settings()

        configured_secret = (
            settings.auth_cookie_secret.get_secret_value()
            if settings.auth_cookie_secret is not None
            else None
        )

        self.secret_key = (
            secret_key
            or configured_secret
            or _PROCESS_COOKIE_SECRET
        )

        self.max_age_seconds = (
            max_age_seconds
            if max_age_seconds is not None
            else settings.auth_cookie_hours * 60 * 60
        )

        if self.max_age_seconds <= 0:
            raise ValueError(
                "Authentication cookie duration must be positive."
            )

        self.serializer = URLSafeTimedSerializer(
            secret_key=self.secret_key,
            salt=_TOKEN_SALT,
        )

    @staticmethod
    def _password_fingerprint(password_hash: str) -> str:
        """Return a non-reversible short fingerprint of a password hash."""

        return hashlib.sha256(
            password_hash.encode("utf-8")
        ).hexdigest()[:24]

    def issue_token(
        self,
        current_user: AuthenticatedUser,
    ) -> str:
        """Create a signed token for an active authenticated user."""

        user = self.user_repository.get_for_password_change(
            company_id=current_user.company_id,
            user_id=current_user.user_id,
        )

        if (
            user is None
            or not user.is_active
            or not user.company.is_active
        ):
            raise SignedCookieAuthenticationError(
                "The user account cannot create a browser session."
            )

        payload = {
            "version": _TOKEN_VERSION,
            "user_id": user.id,
            "company_id": user.company_id,
            "password_fingerprint": (
                self._password_fingerprint(user.password_hash)
            ),
        }

        return self.serializer.dumps(payload)

    def restore_user(
        self,
        token: str,
    ) -> AuthenticatedUser:
        """Validate a signed token and return current database user data."""

        if not token or len(token) > 4096:
            raise SignedCookieAuthenticationError(
                "The authentication cookie is invalid."
            )

        try:
            payload: Any = self.serializer.loads(
                token,
                max_age=self.max_age_seconds,
            )
        except SignatureExpired as error:
            raise SignedCookieAuthenticationError(
                "The authentication cookie has expired."
            ) from error
        except BadSignature as error:
            raise SignedCookieAuthenticationError(
                "The authentication cookie signature is invalid."
            ) from error

        if not isinstance(payload, dict):
            raise SignedCookieAuthenticationError(
                "The authentication cookie payload is invalid."
            )

        if payload.get("version") != _TOKEN_VERSION:
            raise SignedCookieAuthenticationError(
                "The authentication cookie version is unsupported."
            )

        try:
            user_id = int(payload["user_id"])
            company_id = int(payload["company_id"])
            cookie_fingerprint = str(
                payload["password_fingerprint"]
            )
        except (KeyError, TypeError, ValueError) as error:
            raise SignedCookieAuthenticationError(
                "The authentication cookie is incomplete."
            ) from error

        user = self.user_repository.get_for_password_change(
            company_id=company_id,
            user_id=user_id,
        )

        if (
            user is None
            or user.company_id != company_id
            or not user.is_active
            or not user.company.is_active
        ):
            raise SignedCookieAuthenticationError(
                "The account is no longer authorized."
            )

        current_fingerprint = self._password_fingerprint(
            user.password_hash
        )

        if not secrets.compare_digest(
            cookie_fingerprint,
            current_fingerprint,
        ):
            raise SignedCookieAuthenticationError(
                "The authentication cookie is no longer valid."
            )

        return AuthenticatedUser.from_model(user)
