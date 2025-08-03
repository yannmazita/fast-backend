# src.features.auth.utils.scopes
from enum import Enum


OAUTH_SCOPES = {
    # Profile Scopes
    "::PROFILE::READ_SELF::": "Read own user profile.",
    "::PROFILE::UPDATE_SELF::": "Update own user profile.",
    "::PROFILE::DELETE_SELF::": "Delete own user account.",
    "::PROFILE::DISABLE_SELF::": "Disable own user account.",
    # User Management Scopes (for admins/moderators)
    "::USERS::CREATE::": "Create new user accounts.",
    "::USERS::LIST::": "List all user accounts.",
    "::USERS::READ_ANY::": "Read any user's profile.",
    "::USERS::UPDATE_ANY::": "Update any user's profile (like  roles, active status).",
    "::USERS::DELETE_ANY::": "Delete any user's account.",
    # Ban Management Scopes
    "::BANS::CREATE::": "Create bans for users.",
    "::BANS::READ_HISTORY_ANY::": "Read ban history for any user.",
    "::BANS::DEACTIVATE::": "Deactivate user bans.",
    # WebSocket Scope
    "::WEBSOCKETS::CONNECT::": "Connect to WebSocket for real-time features.",
    # User Data Export Scope
    "::USER_DATA::EXPORT_SELF::": "Export own user data.",
    # Premium
    "::SOME_PREMIUM_FEATURE::SOME_ACTION::": "Example premium scope",
    # Content management
    "::SOME_CONTENT_ADMIN_FEATURE::SOME_ACTION::": "Example content management scope",
}


# Utility function to get all defined scope keys
def get_all_defined_scopes() -> set[str]:
    return set(OAUTH_SCOPES.keys())


class UserRoles(str, Enum):
    """
    Defines the abstract user roles within the backend.
    These roles are assigned to users and then mapped to specific granular scopes.
    """

    REGULAR = "REGULAR"
    PREMIUM = "PREMIUM"  # pay up, gang
    GUEST = "GUEST"
    MODERATOR = "MODERATOR"
    CONTENT_ADMIN = "CONTENT_ADMIN"
    ADMINISTRATOR = "ADMINISTRATOR"

    @classmethod
    def get_all_roles(cls) -> list[str]:
        return [role.value for role in cls]
