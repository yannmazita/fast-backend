# src.features.users.router
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Security, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.database import get_session
from src.core.exceptions import (
    BadRequestError,
    DuplicateResource,
    PermissionDenied,
    ResourceNotFound,
)
from src.features.auth.schemas import TokenData
from src.features.auth.utils.dependencies import (
    validate_token,
)
from src.features.users.models import User
from src.features.users.repository import UserRepository
from src.features.users.schemas import (
    UserCreate,
    UserRead,
    UserUpdate,
    BanCreate,
    BanRead,
)

from src.features.users.services.users import UserService
from src.features.users.utils.dependencies import (
    get_own_user,
    get_user_by_id_dependency,
)
from src.features.users.utils.export_schemas import UserDataExport


router = APIRouter(
    prefix="/users",
    tags=["users"],
)

# --- "Me" endpoints ---


@router.get("/me", response_model=UserRead)
async def get_own_user_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[
        User, Security(get_own_user, scopes=["::PROFILE::READ_SELF::"])
    ],
    user_service: Annotated[UserService, Depends()],
):
    """
    Retrieves the profile of the currently authenticated user.
    """
    return await user_service.get_user_with_rank(session, current_user)


async def _update_user(
    session: AsyncSession,
    user_service: UserService,
    user_to_update: User,
    update_data: UserUpdate,
) -> User:
    """Helper function to update a user's profile."""
    updated_user = user_to_update
    if update_data.username is not None and update_data.username != user_to_update.username:
        updated_user = await user_service.update_username(
            session, user_to_update.id, update_data.username
        )

    if update_data.email is not None and update_data.email != user_to_update.email:
        updated_user = await user_service.user_repository.update_by_attribute(
            session, {"email": update_data.email}, user_to_update.id, "id"
        )

    if update_data.roles is not None:
        updated_user = await user_service.update_roles(
            session, user_to_update.id, update_data.roles
        )

    if (
        update_data.is_active is not None
        and update_data.is_active != user_to_update.is_active
    ):
        updated_user = await user_service.update_user_active_status(
            session, user_to_update.id, update_data.is_active
        )

    return updated_user


@router.patch("/me", response_model=UserRead)
async def update_own_profile(
    user_update_data: UserUpdate,
    current_user: Annotated[
        User, Security(get_own_user, scopes=["::PROFILE::UPDATE_SELF::"])
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    user_service: Annotated[UserService, Depends()],
):
    """
    Updates the profile information (username, email...) for the currently authenticated user.
    Password updates disabled to avoid converting oauth accounts to internal accounts.
    """
    return await _update_user(session, user_service, current_user, user_update_data)


@router.post("/me/disable", response_model=UserRead, status_code=status.HTTP_200_OK)
async def disable_own_account(
    current_user: Annotated[
        User, Security(get_own_user, scopes=["::PROFILE::DISABLE_SELF::"])
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    user_service: Annotated[UserService, Depends()],
):
    """
    Allows the currently authenticated user to self-disable their account.
    The account can be re-activated by logging in within a grace period.
    """
    disabled_user = await user_service.disable_account(session, current_user.id)
    return disabled_user


@router.delete("/me", response_model=UserRead)
async def delete_own_user_endpoint(
    current_user: Annotated[
        User, Security(get_own_user, scopes=["::PROFILE::DELETE_SELF::"])
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    user_repository: Annotated[UserRepository, Depends()],
    user_service: Annotated[UserService, Depends()],
):
    """
    Allows the currently authenticated user to permanently delete their account.
    This action is irreversible.
    """
    # First, prepare the response data while the user object still exists
    # and its relations can be resolved to compute the rank.
    user_to_return = await user_service.get_user_with_rank(session, current_user)
    await user_repository.delete(session, current_user.id)
    return user_to_return


@router.get("/me/data-export", response_model=UserDataExport)
async def export_own_user_data_endpoint(
    current_user: Annotated[
        User, Security(get_own_user, scopes=["::USER_DATA::EXPORT_SELF::"])
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    user_service: Annotated[UserService, Depends()],
):
    """
    Exports all personal data for the currently authenticated user.
    This includes profile information, linked OAuth accounts, ban history,
    and detailed game session history.
    """
    user_export_data = await user_service.export_user_data(session, current_user)
    return user_export_data


# --- Admin/Moderator User Management Endpoints ---


@router.post("/reset-all-stats", status_code=status.HTTP_204_NO_CONTENT)
async def reset_all_player_stats(
    token_data: Annotated[
        TokenData, Security(validate_token, scopes=["::USERS::UPDATE_ANY::"])
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    user_service: Annotated[UserService, Depends()],
):
    """
    Resets all player stats (XP, MMR, etc.) to their default values.
    This is a destructive operation and should be used with caution.
    """
    await user_service.reset_all_player_stats(session)
    return


@router.post(
    "/",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_user_by_admin(
    user_data: UserCreate,
    token_data: Annotated[
        TokenData, Security(validate_token, scopes=["::USERS::CREATE::"])
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    user_service: Annotated[UserService, Depends()],
):
    """
    Creates a new user. This endpoint is typically restricted to administrators.
    Allows setting username, email, password, and roles.
    """
    try:
        new_user = await user_service.create_user(session, user_data)
        return new_user
    except DuplicateResource as e:
        detail = "A user with this username or email already exists."
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from e


@router.get(
    "/{user_id}",
    response_model=UserRead,
)
async def get_user_by_id_admin(
    target_user: Annotated[User, Depends(get_user_by_id_dependency)],
    token_data: Annotated[
        TokenData, Security(validate_token, scopes=["::USERS::READ_ANY::"])
    ],
):
    """
    Retrieves the profile information for a specific user by their ID.
    Requires administrator or appropriate moderator privileges.
    """
    return target_user


@router.patch(
    "/{user_id}",
    response_model=UserRead,
)
async def update_user_by_id_admin(
    user_update_data: UserUpdate,
    target_user: Annotated[User, Depends(get_user_by_id_dependency)],
    token_data: Annotated[
        TokenData, Security(validate_token, scopes=["::USERS::UPDATE_ANY::"])
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    user_service: Annotated[UserService, Depends()],
):
    """
    Updates the profile information for a specific user by their ID.
    Allows modification of username, email, roles, and active status.
    Requires administrator or appropriate moderator privileges.
    """
    return await _update_user(session, user_service, target_user, user_update_data)


@router.delete(
    "/{user_id}",
    response_model=UserRead,
)
async def delete_user_by_id_admin(
    target_user: Annotated[User, Depends(get_user_by_id_dependency)],
    token_data: Annotated[
        TokenData, Security(validate_token, scopes=["::USERS::DELETE_ANY::"])
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    user_repository: Annotated[UserRepository, Depends()],
    user_service: Annotated[UserService, Depends()],
):
    """
    Deletes a specific user by their ID.
    This action is irreversible. Requires administrator privileges.
    """
    user_to_return = await user_service.get_user_with_rank(session, target_user)
    await user_repository.delete(session, target_user.id)

    return user_to_return


@router.get(
    "/",
    response_model=tuple[list[UserRead], int],
)
async def get_all_users_admin(
    token_data: Annotated[
        TokenData, Security(validate_token, scopes=["::USERS::LIST::"])
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    user_service: Annotated[UserService, Depends()],
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
):
    """
    Lists all users with pagination.
    Requires administrator or appropriate moderator privileges.
    Returns a list of users and the total count of users.
    """
    users, total_count = await user_service.get_all_users_with_rank(
        session, offset, limit
    )
    return users, total_count


# --- Ban Management Endpoints (Admin/Moderator) ---


@router.post(
    "/{user_id}/bans", response_model=BanRead, status_code=status.HTTP_201_CREATED
)
async def create_user_ban(
    user_id: UUID,  # This is the user_id of the user to be banned
    ban_data: BanCreate,
    token_data: Annotated[
        TokenData, Security(validate_token, scopes=["::BANS::CREATE::"])
    ],  # Use new scope
    session: Annotated[AsyncSession, Depends(get_session)],
    user_service: Annotated[UserService, Depends()],
):
    """
    Creates a ban for a specified user.
    Allows setting a reason and an expiration date for the ban.
    If no expiration date is provided, the ban is permanent.
    Requires moderator or administrator privileges.
    """
    if ban_data.user_id != user_id:  # Ensure consistency
        raise BadRequestError("User ID in path does not match user ID in request body.")

    admin_user_id_from_token = UUID(str(token_data.uid))
    if (
        not admin_user_id_from_token
    ):  # Should not happen if token is valid and contains uid
        raise PermissionDenied("Admin user ID not found in token for auditing.")

    try:
        new_ban = await user_service.create_ban(
            session, ban_data, admin_user_id_from_token
        )
        return new_ban
    except ResourceNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User to ban not found."
        )
    except BadRequestError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e.detail)
        )


@router.get("/{user_id}/bans", response_model=tuple[list[BanRead], int])
async def get_user_ban_history_endpoint(
    user_id: UUID,  # User ID whose ban history is being fetched
    token_data: Annotated[
        TokenData,
        Security(
            validate_token, scopes=["::BANS::READ_HISTORY_ANY::"]
        ),  # Use new scope
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    user_service: Annotated[UserService, Depends()],
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
):
    """
    Retrieves the ban history for a specific user, paginated.
    Requires moderator or administrator privileges.
    Returns a list of bans and the total count of bans for that user.
    """
    try:
        bans, total_count = await user_service.get_user_ban_history(
            session, user_id, offset, limit
        )
        return bans, total_count
    except ResourceNotFound:  # If the user_id itself is not found
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
        )


@router.patch("/bans/{ban_id}/deactivate", response_model=BanRead)
async def deactivate_user_ban(
    ban_id: UUID,
    token_data: Annotated[
        TokenData, Security(validate_token, scopes=["::BANS::DEACTIVATE::"])
    ],  # Use new scope
    session: Annotated[AsyncSession, Depends(get_session)],
    user_service: Annotated[UserService, Depends()],
):
    """
    Deactivates an existing ban, making it no longer effective.
    This does not delete the ban record but marks it as inactive.
    Requires moderator or administrator privileges.
    """
    admin_user_id_from_token = UUID(str(token_data.uid))
    if not admin_user_id_from_token:  # Should not happen
        raise PermissionDenied("Admin user ID not found in token for auditing.")
    try:
        updated_ban = await user_service.deactivate_ban(
            session, ban_id, admin_user_id_from_token
        )
        return updated_ban
    except ResourceNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ban not found."
        )
