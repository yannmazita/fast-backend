# src.core.exceptions
from datetime import datetime


class AppException(Exception):
    """Base class for application-specific exceptions."""

    status_code: int = 400

    def __init__(self, detail: str | None = None):
        self.detail = detail or getattr(self, "detail", "Application error")
        super().__init__(self.detail)


class ResourceNotFound(AppException):
    """Raised when a requested resource is not found."""

    status_code = 404
    detail = "The requested resource was not found."


class DuplicateResource(AppException):
    """Raised when attempting to create a resource that already exists (violating uniqueness)."""

    status_code = 409
    detail = "This resource already exists."


class InvalidCredentials(AppException):
    """Raised when authentication fails due to incorrect credentials."""

    status_code = 401
    detail = "Incorrect username or password."


class PermissionDenied(AppException):
    """Raised when an action is forbidden for the authenticated user."""

    status_code = 403
    detail = "You do not have permission to perform this action."
    """Raised for general bad requests or validation errors not caught by Pydantic."""


class BadRequestError(AppException):
    """Raised for general bad requests or validation errors not caught by Pydantic."""

    detail = "Bad request."


class UserDisabledError(AppException):
    """Raised when a user account is disabled."""

    status_code = 403  # Forbidden
    detail = "This account has been disabled."

    def __init__(self, detail: str | None = None, permanently_disabled: bool = False):
        custom_detail = detail or self.detail
        if permanently_disabled:
            custom_detail = (
                "This account has been permanently disabled and is pending deletion."
            )
        super().__init__(custom_detail)


class UserBannedError(AppException):
    """Raised when a user account is banned."""

    status_code = 403  # Forbidden
    detail = "This account is currently banned."

    def __init__(
        self,
        detail: str | None = None,
        ban_reason: str | None = None,
        ban_expires_at: datetime | None = None,
    ):
        custom_detail = detail or self.detail
        if ban_reason:
            custom_detail += f" Reason: {ban_reason}."
        if ban_expires_at:
            custom_detail += f" The ban will expire on {ban_expires_at.strftime('%Y-%m-%d %H:%M UTC')}."
        else:  # Permanent ban
            custom_detail += " This ban is permanent."
        super().__init__(custom_detail)
