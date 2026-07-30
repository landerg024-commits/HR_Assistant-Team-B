"""Secure forgot-password and administrator reset business logic.

Security properties:
- Generic request response prevents account enumeration.
- Raw reset tokens are never stored in the database.
- Tokens expire, are single-use, and previous links are revoked.
- Reset email goes only to matching registered Login Email accounts.
- Password changes invalidate signed refresh cookies through their password
  fingerprint.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import logging
import secrets
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from authentication.password_manager import PasswordManager
from config.settings import Settings, get_settings
from integrations.email.email_sender import (
    EmailSender,
    OutboundEmail,
    build_email_sender,
)
from models.password_reset_token import PasswordResetToken
from repositories.company_repository import CompanyRepository
from repositories.password_reset_token_repository import (
    PasswordResetTokenRepository,
)
from repositories.user_repository import UserRepository


LOGGER = logging.getLogger(__name__)

GENERIC_RESET_REQUEST_MESSAGE = (
    "If an active account matches that email, "
    "password reset instructions have been sent."
)


class PasswordResetError(ValueError):
    """Raised when a reset link or new password is invalid."""


@dataclass(slots=True)
class PasswordResetRequestResult:
    """Always-safe result returned to the public forgot-password page."""

    message: str = GENERIC_RESET_REQUEST_MESSAGE


class PasswordResetService:
    """Request, validate, consume, and administratively reset passwords."""

    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        email_sender: EmailSender | None = None,
        password_manager: PasswordManager | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.email_sender = (
            email_sender
            or build_email_sender(self.settings)
        )
        self.password_manager = (
            password_manager or PasswordManager()
        )

        self.user_repository = UserRepository(session)
        self.token_repository = (
            PasswordResetTokenRepository(session)
        )

    @staticmethod
    def _now() -> datetime:
        """Return timezone-aware UTC."""

        return datetime.now(timezone.utc)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        """Normalize SQLite naive timestamps to UTC."""

        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

    @staticmethod
    def _token_hash(raw_token: str) -> str:
        """Return the irreversible database lookup hash."""

        return sha256(
            raw_token.encode("utf-8")
        ).hexdigest()

    def _build_reset_link(
        self,
        raw_token: str,
        *,
        company_code: str,
    ) -> str:
        """Build the public reset URL sent to the employee."""

        base_url = (
            self.settings.password_reset_base_url
            .strip()
            .rstrip("/")
        )

        query = urlencode(
            {
                "auth": "reset",
                "token": raw_token,
                "company": company_code,
            }
        )

        return f"{base_url}/?{query}"

    def _build_reset_email(
        self,
        *,
        company_name: str,
        username: str,
        email: str,
        reset_link: str,
    ) -> OutboundEmail:
        """Create a plain-text reset message without any password."""

        minutes = self.settings.password_reset_token_minutes

        body = (
            f"Hello {username},\n\n"
            f"A password reset was requested for your "
            f"{company_name} HR account.\n\n"
            f"Open this secure link to create a new password:\n"
            f"{reset_link}\n\n"
            f"This link expires in {minutes} minutes and can be "
            f"used only once.\n\n"
            "If you did not request this reset, ignore this email "
            "and your password will remain unchanged.\n\n"
            "For security, the system will never email your existing "
            "password."
        )

        return OutboundEmail(
            to_email=email,
            subject="Reset your HR Assistant password",
            text_body=body,
        )

    def request_reset(
        self,
        *,
        email: str,
    ) -> PasswordResetRequestResult:
        """Issue reset links using only the registered Login Email.

        The public page never asks for a company code. When the same email
        belongs to active accounts in multiple companies, each account gets
        its own company-labeled reset email and independently bound token.
        """

        normalized_email = email.strip().lower()

        users = (
            self.user_repository
            .list_by_email_for_password_reset(
                email=normalized_email,
            )
        )

        eligible_users = [
            user
            for user in users
            if (
                user.is_active
                and user.company.is_active
                and user.clearance in {1, 2}
            )
        ]

        for user in eligible_users:
            self._request_reset_for_user(user)

        return PasswordResetRequestResult()

    def _request_reset_for_user(
        self,
        user,
    ) -> None:
        """Create and deliver one company-bound reset link."""

        now = self._now()
        latest = self.token_repository.get_latest_for_user(
            company_id=user.company_id,
            user_id=user.id,
        )

        if latest is not None:
            elapsed = (
                now
                - self._as_utc(latest.requested_at)
            ).total_seconds()

            if (
                elapsed
                < self.settings
                .password_reset_request_cooldown_seconds
            ):
                return

        self.token_repository.revoke_active_for_user(
            company_id=user.company_id,
            user_id=user.id,
            revoked_at=now,
        )

        raw_token = secrets.token_urlsafe(48)
        reset_record = PasswordResetToken(
            company_id=user.company_id,
            user_id=user.id,
            token_hash=self._token_hash(raw_token),
            delivery_email=user.email,
            requested_at=now,
            expires_at=(
                now
                + timedelta(
                    minutes=(
                        self.settings
                        .password_reset_token_minutes
                    )
                )
            ),
            delivery_status="pending",
        )

        self.session.add(reset_record)
        self.session.commit()
        self.session.refresh(reset_record)

        reset_link = self._build_reset_link(
            raw_token,
            company_code=user.company.code,
        )
        message = self._build_reset_email(
            company_name=user.company.name,
            username=user.username,
            email=user.email,
            reset_link=reset_link,
        )

        try:
            self.email_sender.send(message)
            reset_record.delivery_status = "sent"
            reset_record.delivered_at = self._now()
            reset_record.delivery_error = None

        except Exception as error:
            # Never disclose account or delivery state on the public page.
            reset_record.delivery_status = "failed"
            reset_record.revoked_at = self._now()
            reset_record.delivery_error = (
                type(error).__name__[:100]
            )
            LOGGER.exception(
                "Password-reset email delivery failed."
            )

        self.session.commit()

    def _get_valid_record(
        self,
        raw_token: str,
        *,
        for_update: bool,
    ):
        """Return a valid token record and active user or raise."""

        if (
            not raw_token
            or len(raw_token) > 512
        ):
            raise PasswordResetError(
                "The password reset link is invalid or expired."
            )

        record = self.token_repository.get_by_hash(
            self._token_hash(raw_token),
            for_update=for_update,
        )

        now = self._now()

        if (
            record is None
            or record.used_at is not None
            or record.revoked_at is not None
            or self._as_utc(record.expires_at) <= now
            or record.delivery_status != "sent"
        ):
            raise PasswordResetError(
                "The password reset link is invalid or expired."
            )

        user = self.user_repository.get_for_password_change(
            company_id=record.company_id,
            user_id=record.user_id,
        )

        if (
            user is None
            or not user.is_active
            or not user.company.is_active
        ):
            raise PasswordResetError(
                "The password reset link is invalid or expired."
            )

        return record, user

    @classmethod
    def get_company_for_valid_token(
        cls,
        session: Session,
        raw_token: str,
    ):
        """Return the active company bound to a valid reset token.

        This is used only for public-page branding. It does not expose the
        account, email, username, or password-reset record.
        """

        if (
            not raw_token
            or len(raw_token) > 512
        ):
            return None

        record = PasswordResetTokenRepository(
            session
        ).get_by_hash(
            cls._token_hash(raw_token),
            for_update=False,
        )

        now = cls._now()

        if (
            record is None
            or record.used_at is not None
            or record.revoked_at is not None
            or cls._as_utc(record.expires_at) <= now
            or record.delivery_status != "sent"
        ):
            return None

        company = CompanyRepository(
            session
        ).get_by_id(record.company_id)

        if company is None or not company.is_active:
            return None

        return company
    def is_token_valid(
        self,
        raw_token: str,
    ) -> bool:
        """Return True without consuming a reset token."""

        try:
            self._get_valid_record(
                raw_token,
                for_update=False,
            )
            return True
        except PasswordResetError:
            return False

    def reset_password(
        self,
        *,
        raw_token: str,
        new_password: str,
    ) -> None:
        """Consume one reset link and store a new Argon2 password."""

        record, user = self._get_valid_record(
            raw_token,
            for_update=True,
        )

        if self.password_manager.verify_password(
            new_password,
            user.password_hash,
        ):
            raise PasswordResetError(
                "The new password must be different "
                "from the current password."
            )

        now = self._now()

        user.password_hash = (
            self.password_manager.hash_password(
                new_password
            )
        )
        user.must_change_password = False
        record.used_at = now

        self.token_repository.revoke_active_for_user(
            company_id=user.company_id,
            user_id=user.id,
            revoked_at=now,
            exclude_token_id=record.id,
        )

        self.session.commit()

    def set_temporary_password_by_admin(
        self,
        *,
        company_id: int,
        user_id: int,
        current_admin_user_id: int,
        temporary_password: str,
    ) -> None:
        """Set a temporary password without revealing the old password."""

        if user_id == current_admin_user_id:
            raise PasswordResetError(
                "Use the account password-change page "
                "to update your own password."
            )

        user = self.user_repository.get_for_password_change(
            company_id=company_id,
            user_id=user_id,
        )

        if user is None:
            raise PasswordResetError(
                "The selected account was not found "
                "inside this company."
            )

        if self.password_manager.verify_password(
            temporary_password,
            user.password_hash,
        ):
            raise PasswordResetError(
                "The temporary password must be different "
                "from the existing password."
            )

        now = self._now()

        user.password_hash = (
            self.password_manager.hash_password(
                temporary_password
            )
        )
        user.must_change_password = True

        self.token_repository.revoke_active_for_user(
            company_id=company_id,
            user_id=user_id,
            revoked_at=now,
        )

        self.session.commit()
