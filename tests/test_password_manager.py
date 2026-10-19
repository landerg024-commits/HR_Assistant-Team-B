"""Password hashing tests."""

from authentication.password_manager import PasswordManager


def test_password_hash_and_verification() -> None:
    """A valid password should verify against its Argon2 hash."""

    manager = PasswordManager()
    password = "SecurePass123!"

    password_hash = manager.hash_password(password)

    assert password_hash != password
    assert password_hash.startswith("$argon2")
    assert manager.verify_password(
        password,
        password_hash,
    )
    assert not manager.verify_password(
        "WrongPassword123!",
        password_hash,
    )
