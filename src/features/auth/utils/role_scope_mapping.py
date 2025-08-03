# src.features.auth.utils.role_scope_mapping
from src.features.auth.utils.scopes import (
    UserRoles,
    OAUTH_SCOPES,
)

# Helper to make sure we are using valid scope keys
ALL_DEFINED_SCOPES = set(OAUTH_SCOPES.keys())


def _validate_scopes(scopes_to_validate: set[str]) -> set[str]:
    invalid_scopes = scopes_to_validate - ALL_DEFINED_SCOPES
    if invalid_scopes:
        raise ValueError(f"Invalid scopes found in role mapping: {invalid_scopes}")
    return scopes_to_validate


REGULAR_USER_SCOPES = _validate_scopes(
    {
        "::PROFILE::READ_SELF::",
        "::PROFILE::UPDATE_SELF::",
        "::PROFILE::DELETE_SELF::",
        "::PROFILE::DISABLE_SELF::",
        "::WEBSOCKETS::CONNECT::",
        "::USER_DATA::EXPORT_SELF::",
    }
)

PREMIUM_USER_SCOPES = _validate_scopes(
    REGULAR_USER_SCOPES
    | {
        "::SOME_PREMIUM_FEATURE::SOME_ACTION::",
    }
)

GUEST_USER_SCOPES = _validate_scopes(
    {
        "::PROFILE::READ_SELF::",
        "::WEBSOCKETS::CONNECT::",
        "::USER_DATA::EXPORT_SELF::",
    }
)

MODERATOR_SCOPES = _validate_scopes(
    REGULAR_USER_SCOPES
    | {
        "::USERS::LIST::",  # To find users
        "::USERS::READ_ANY::",  # To view user details before action
        "::BANS::CREATE::",
        "::BANS::READ_HISTORY_ANY::",
        "::BANS::DEACTIVATE::",
    }
)

CONTENT_ADMIN_SCOPES = _validate_scopes(
    REGULAR_USER_SCOPES
    | {
        # Content admin can also be players.
        "::SOME_CONTENT_ADMIN_FEATURE::SOME_ACTION::",
    }
)

# ADMINISTRATOR gets all defined scopes for maximum control.
# Please be careful with this.
ADMINISTRATOR_SCOPES = _validate_scopes(ALL_DEFINED_SCOPES.copy())


ROLE_SCOPES_MAPPING = {
    UserRoles.REGULAR: REGULAR_USER_SCOPES,
    UserRoles.PREMIUM: PREMIUM_USER_SCOPES,
    UserRoles.GUEST: GUEST_USER_SCOPES,
    UserRoles.MODERATOR: MODERATOR_SCOPES,
    UserRoles.CONTENT_ADMIN: CONTENT_ADMIN_SCOPES,
    UserRoles.ADMINISTRATOR: ADMINISTRATOR_SCOPES,
}


def get_scopes_for_roles(roles: list[UserRoles]) -> set[str]:
    """
    Aggregates all unique scopes for a given list of UserRoles.
    """
    granted_scopes = set()
    for role in roles:
        granted_scopes.update(ROLE_SCOPES_MAPPING.get(role, set()))
    return granted_scopes


def get_scopes_for_role_strings(role_strings: list[str]) -> set[str]:
    """
    Aggregates all unique scopes for a given list of role name strings.
    Filters out any invalid role strings.
    """
    granted_scopes = set()
    for role_str in role_strings:
        try:
            role_enum = UserRoles(role_str)
            granted_scopes.update(ROLE_SCOPES_MAPPING.get(role_enum, set()))
        except ValueError:
            # Ignoring
            pass
    return granted_scopes
