"""Password hashing helper using Argon2.

Purpose:
- Convert plain-text passwords into secure hashes.
- Verify login passwords without exposing the stored password.
- Detect old hashes that should be upgraded later.
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError


class PasswordManager:
    """Hash and verify passwords using Argon2."""

    def __init__(self) -> None:
        self._hasher = PasswordHasher()

    def hash_password(self, password: str) -> str:
        """Return a secure hash for a valid plain-text password."""

        if not password or len(password) < 8:
            raise ValueError(
                "Password must contain at least 8 characters."
            )

        return self._hasher.hash(password)

    def verify_password(
        self,
        password: str,
        password_hash: str,
    ) -> bool:
        """Return True when the password matches the stored hash."""

        try:
            return self._hasher.verify(
                password_hash,
                password,
            )
        except (VerifyMismatchError, InvalidHashError):
            # Invalid credentials should return False, not crash the app.
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        """Return True when Argon2 recommends generating a newer hash."""

        try:
            return self._hasher.check_needs_rehash(password_hash)
        except InvalidHashError:
            return True
