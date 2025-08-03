# src.features.auth.schemas
from uuid import UUID
from pydantic import ConfigDict, EmailStr, field_validator
from src.core.schemas import Base as CoreBaseSchema, UuidMixin
from src.features.users.models import User
from enum import Enum
from datetime import datetime


class Token(CoreBaseSchema):
    access_token: str | None
    token_type: str | None
    expires_at: datetime | None = None


class TokenFullDetail(CoreBaseSchema):
    access_token: str
    token_type: str
    refresh_token: str
    expires_at: datetime


class GuestLoginResponse(Token):
    guest_user_id: UUID


class TokenData(CoreBaseSchema):
    sub: str | None = None
    uid: UUID | None = None
    roles: list[str] = []
    scopes: list[str] = []
    is_guest: bool | None = False


class RefreshTokenData(CoreBaseSchema):
    sub: str  # username
    uid: UUID
    jti: str  # JWT ID, to link with DB record
    exp: datetime
    purpose: str = "refresh"


class OAuthAccountBase(CoreBaseSchema):
    oauth_name: str
    provider_user_id: str
    provider_email: EmailStr | None = None


class OAuthAccountCreate(OAuthAccountBase):
    pass


class OAuthAccountRead(OAuthAccountBase, UuidMixin):
    user_id: UUID


class OAuthPendingRegistrationData(CoreBaseSchema):
    provider_name: str
    provider_user_id: str
    provider_email: EmailStr | None = None
    provider_display_name: str | None = None
    exp: datetime
    purpose: str = "oauth_pending_registration"


class OAuthFlowStatus(str, Enum):
    USER_AUTHENTICATED = "USER_AUTHENTICATED"
    USERNAME_REGISTRATION_REQUIRED = "USERNAME_REGISTRATION_REQUIRED"


class OAuthAuthenticationResult(CoreBaseSchema):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    status: OAuthFlowStatus
    user: User | None = None
    pending_registration_token: str | None = None


class CompleteOAuthRegistrationRequest(CoreBaseSchema):
    pending_token: str
    username: str

    @field_validator("username")
    @classmethod
    def validate_username_length(cls, value: str):
        if len(value) < 3:
            raise ValueError("Username must be at least 3 characters.")
        if len(value) > 50:
            raise ValueError("Username must be at most 50 characters.")
        if not value.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Username can only contain letters, numbers, _ and -")
        return value
