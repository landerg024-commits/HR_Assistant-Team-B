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
not configured, a private local signing-secret file is created. This keeps
a valid browser login across both page refreshes and Streamlit restarts.
"""

import hashlib
import os
from pathlib import Path
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


_EMERGENCY_PROCESS_COOKIE_SECRET = secrets.token_urlsafe(48)
_TOKEN_SALT = "ai-hr-assistant-auth-cookie-v1"
_TOKEN_VERSION = 1


def _clean_configured_secret(value: str | None) -> str | None:
    """Return a usable configured secret or None for an empty value."""

    if not isinstance(value, str):
        return None

    cleaned = value.strip()

    return cleaned if len(cleaned) >= 32 else None


def _read_secret_file(path: Path) -> str | None:
    """Read a valid local cookie secret without exposing its value."""

    try:
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None

    return value if len(value) >= 32 else None


def _load_or_create_local_secret(path_value: str) -> str:
    """Load or atomically create the private local signing secret."""

    path = Path(path_value).expanduser()
    existing = _read_secret_file(path)

    if existing is not None:
        return existing

    generated = secrets.token_urlsafe(64)

    try:
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        descriptor = os.open(
            str(path),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )

        with os.fdopen(
            descriptor,
            "w",
            encoding="utf-8",
        ) as secret_file:
            secret_file.write(generated)
            secret_file.write("\n")

        try:
            path.chmod(0o600)
        except OSError:
            # Windows may not apply POSIX permissions; the file remains
            # private inside the application data directory.
            pass

        return generated

    except FileExistsError:
        # Another Streamlit execution context created it first.
        return (
            _read_secret_file(path)
            or _EMERGENCY_PROCESS_COOKIE_SECRET
        )
    except OSError:
        # Authentication stays usable even on read-only filesystems, but
        # server-restart persistence then requires AUTH_COOKIE_SECRET.
        return _EMERGENCY_PROCESS_COOKIE_SECRET


def resolve_auth_cookie_secret(settings) -> str:
    """Resolve configured or persistent local cookie-signing material."""

    configured = (
        settings.auth_cookie_secret.get_secret_value()
        if settings.auth_cookie_secret is not None
        else None
    )
    cleaned = _clean_configured_secret(configured)

    if cleaned is not None:
        return cleaned

    return _load_or_create_local_secret(
        settings.auth_cookie_secret_file
    )


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

        self.secret_key = (
            secret_key
            or resolve_auth_cookie_secret(settings)
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
