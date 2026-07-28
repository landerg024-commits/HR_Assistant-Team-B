"""Pydantic validation schemas for login and password changes."""

from pydantic import BaseModel, EmailStr, Field, model_validator


class LoginRequest(BaseModel):
    """Validated values submitted by the login form."""

    company_code: str = Field(min_length=1, max_length=50)
    login_identifier: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class PasswordChangeRequest(BaseModel):
    """Validated values submitted by the password-change form."""

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def passwords_must_match(self):
        """Reject mismatched password confirmation."""

        if self.new_password != self.confirm_password:
            raise ValueError(
                "New password and confirmation do not match."
            )

        return self



class ForgotPasswordRequest(BaseModel):
    """Validated registered Login Email for password recovery."""

    email: EmailStr


class PasswordResetCompletionRequest(BaseModel):
    """Validated new password submitted from a reset link."""

    new_password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def passwords_must_match(self):
        """Require the same new password twice."""

        if self.new_password != self.confirm_password:
            raise ValueError(
                "New password and confirmation do not match."
            )

        return self


class AdminTemporaryPasswordRequest(BaseModel):
    """Validated temporary password assigned by an administrator."""

    temporary_password: str = Field(
        min_length=8,
        max_length=128,
    )
    confirm_password: str = Field(
        min_length=8,
        max_length=128,
    )

    @model_validator(mode="after")
    def passwords_must_match(self):
        """Require matching administrator-entered passwords."""

        if (
            self.temporary_password
            != self.confirm_password
        ):
            raise ValueError(
                "Temporary password and confirmation "
                "do not match."
            )

        return self
