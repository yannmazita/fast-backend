# src.features.users.schemas
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, field_validator, model_validator, EmailStr

from src.core.exceptions import BadRequestError
from src.core.schemas import Base as CoreBaseSchema, UuidMixin
from src.features.auth.utils.scopes import UserRoles

DEFAULT_USER_ROLE = UserRoles.REGULAR.value


class UserBase(CoreBaseSchema):
    username: str
    email: EmailStr | None = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str):
        if not value:
            raise ValueError("Username cannot be empty.")
        if len(value) < 3:
            raise ValueError("Username must be at least 3 characters.")
        if len(value) > 50:
            raise ValueError("Username must be at most 50 characters.")
        # Basic alphanumeric, underscore, hyphen check
        if not value.replace("_", "").replace("-", "").isalnum():  # Allow _ and -
            raise ValueError("Username can only contain letters, numbers, _ and -")
        return value


class UserCreate(UserBase):
    password: str | None = None
    confirm_password: str | None = None
    is_guest: bool = False
    ip_address: str | None = None
    roles: str

    @model_validator(mode="after")
    def validate_passwords_on_create(self) -> "UserCreate":
        if self.password and self.password != self.confirm_password:
            raise BadRequestError("Password and confirmation password do not match.")
        # Todo: complexity requirements
        return self

    @field_validator("roles")
    @classmethod
    def validate_roles_values(cls, value: str):
        # Validate against the defined UserRoles enum values
        valid_roles_from_enum = set(UserRoles.get_all_roles())
        if value.strip() == "":
            given_roles = set()
        else:
            given_roles = set(value.split())

        if not given_roles.issubset(valid_roles_from_enum):
            invalid = given_roles - valid_roles_from_enum
            raise ValueError(f"Invalid roles provided: {', '.join(invalid)}")
        return value  # Return the space-separated string of valid roles


class UserUpdate(CoreBaseSchema):
    username: str | None = None
    email: EmailStr | None = None
    # old_password: str | None = None
    # new_password: str | None = None
    # confirm_password: str | None = None
    roles: str | None = None  # Space-separated string of UserRoles values
    is_active: bool | None = None  # For admin to activate/deactivate

    #
    # Updatating user passwords (of internal accounts) is disabled as
    # internal accounts are currently meant for administration and testing.
    #
    # @model_validator(mode="after")
    # def validate_passwords_on_update(self) -> "UserUpdate":
    #    if self.new_password:
    #        if self.new_password != self.confirm_password:
    #            raise BadRequestError(
    #                "New password and confirmation password do not match."
    #            )
    #        if self.old_password and self.old_password == self.new_password:
    #            raise BadRequestError(
    #                "New password cannot be the same as the old password."
    #            )
    #    elif self.old_password and not self.new_password:
    #        raise BadRequestError(
    #            "New password must be provided if old password is set for a change."
    #        )
    #    return self

    @field_validator("username")
    @classmethod
    def validate_username_length(cls, value: str | None):
        if value is not None:
            if len(value) < 3:
                raise BadRequestError("Username must be at least 3 characters.")
            if len(value) > 50:
                raise BadRequestError("Username must be at most 50 characters.")
        return value

    @field_validator("roles")
    @classmethod
    def validate_roles_values_optional(cls, value: str | None):
        if value is not None:
            valid_roles_from_enum = set(UserRoles.get_all_roles())
            if value.strip() == "":  # Allow empty string to mean "remove all roles"
                given_roles = set()
            else:
                given_roles = set(value.split())

            if not given_roles.issubset(valid_roles_from_enum):
                invalid = given_roles - valid_roles_from_enum
                raise ValueError(f"Invalid roles provided: {', '.join(invalid)}")
        return value


class UserRead(UserBase, UuidMixin):
    roles: str
    is_active: bool
    is_guest: bool
    disabled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class BanBase(CoreBaseSchema):
    reason: str | None = None
    expires_at: datetime | None = None


class BanCreate(BanBase):
    user_id: UUID


class BanRead(BanBase, UuidMixin):
    user_id: UUID
    banned_at: datetime
    banned_by_id: UUID | None = None
    is_currently_active: bool
    deactivated_at: datetime | None = None
    deactivated_by_id: UUID | None = None


class UserWithBans(UserRead):
    bans_received: list[BanRead] = []


class Users(BaseModel):
    users: list[UserRead]
    total: int
