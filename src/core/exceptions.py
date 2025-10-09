# src.core.exceptions
from datetime import datetime


class AppException(Exception):
    """Base class for all application-specific exceptions.

    Provides a default status code and detail message that can be
    overridden by subclasses.

    Attributes:
        status_code: The HTTP status code to be returned for this exception.
        detail: A descriptive message for the error.
    """

    status_code: int = 400

    def __init__(self, detail: str | None = None):
        """Initializes the application exception.

        Args:
            detail: An optional override for the default detail message.
        """
        self.detail = detail or getattr(self, "detail", "Application error")
        super().__init__(self.detail)


class ResourceNotFound(AppException):
    """Raised when a requested resource is not found in the database."""

    status_code = 404
    detail = "The requested resource was not found."


class DuplicateResource(AppException):
    """Raised when creating a resource that violates a uniqueness constraint."""

    status_code = 409
    detail = "This resource already exists."


class InvalidCredentials(AppException):
    """Raised during authentication when provided credentials are incorrect."""

    status_code = 401
    detail = "Incorrect username or password."


class PermissionDenied(AppException):
    """Raised when an authenticated user lacks permission for an action."""

    status_code = 403
    detail = "You do not have permission to perform this action."


class BadRequestError(AppException):
    """Raised for general bad requests or validation errors."""

    detail = "Bad request."


class UserDisabledError(AppException):
    """Raised when a user account is disabled and access is attempted.

    This exception handles both temporary (self-disabled) and permanent
    (past grace period) disablement states.
    """

    status_code = 403  # Forbidden
    detail = "This account has been disabled."

    def __init__(self, detail: str | None = None, permanently_disabled: bool = False):
        """Initializes the user disabled error.

        Args:
            detail: An optional override for the default detail message.
            permanently_disabled: If True, a specific message indicating
                                  permanent disablement is used.
        """
        custom_detail = detail or self.detail
        if permanently_disabled:
            custom_detail = (
                "This account has been permanently disabled and is pending deletion."
            )
        super().__init__(custom_detail)


class UserBannedError(AppException):
    """Raised when a user account is banned and access is attempted."""

    status_code = 403  # Forbidden
    detail = "This account is currently banned."

    def __init__(
        self,
        detail: str | None = None,
        ban_reason: str | None = None,
        ban_expires_at: datetime | None = None,
    ):
        """Initializes the user banned error with ban details.

        Args:
            detail: An optional override for the default detail message.
            ban_reason: The reason for the ban.
            ban_expires_at: The timestamp when the ban expires. If None,
                            the ban is considered permanent.
        """
        custom_detail = detail or self.detail
        if ban_reason:
            custom_detail += f" Reason: {ban_reason}."
        if ban_expires_at:
            custom_detail += f" The ban will expire on {ban_expires_at.strftime('%Y-%m-%d %H:%M UTC')}."
        else:  # Permanent ban
            custom_detail += " This ban is permanent."
        super().__init__(custom_detail)
