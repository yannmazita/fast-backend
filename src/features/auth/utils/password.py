# src.features.auth.utils.password
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

ph = PasswordHasher()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain-text password against a hashed password.

    Args:
        plain_password: The plain-text password to verify.
        hashed_password: The hashed password to verify against.

    Returns:
        bool: True if the password is correct, False otherwise.
    """
    try:
        return ph.verify(hashed_password, plain_password)
    except VerifyMismatchError:
        return False


def get_password_hash(password: str) -> str:
    """Generates a hash for a plain-text password.

    Args:
        password: The plain-text password to hash.

    Returns:
        The hashed password.
    """
    return ph.hash(password)
