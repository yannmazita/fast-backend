# src/features/users/utils/dependencies.py
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.database import get_session
from src.features.auth.schemas import TokenData
from src.features.auth.utils.dependencies import validate_token, validate_token_optional
from src.features.users.models import User
from src.features.users.repository import UserRepository


async def get_user_by_id_dependency(
    user_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user_repo: Annotated[UserRepository, Depends()],
) -> User:
    """
    Dependency to fetch a user by ID.
    Raises a 404 NOT FOUND error if the user does not exist.
    """
    user = await user_repo.get_by_attribute(session, user_id, "id")
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
        )
    return user


async def get_own_user(
    token_data: Annotated[TokenData, Depends(validate_token)],
    user_repo: Annotated[UserRepository, Depends()],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    """
    Dependency to get the currently authenticated user from the database.
    """
    user_id = token_data.uid
    return await get_user_by_id_dependency(
        user_id,  # type: ignore
        session,
        user_repo,
    )


async def get_optional_user(
    token_data: Annotated[
        TokenData | None,
        Depends(validate_token_optional),
    ],
    user_repo: Annotated[UserRepository, Depends()],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User | None:
    """
    Retrieves the currently authenticated user when available.

    This dependency is intended for endpoints that allow both
    authenticated and anonymous access. If no valid access token
    is provided, None is returned. If a valid token is present,
    the corresponding user is loaded from the database.

    Returns:
            The authenticated user if one can be resolved from the
            supplied token, otherwise None.

    Raises:
        HTTPException:
            If a valid token references a user that no longer exists.
        PermissionDenied:
            Propagated from token validation when required scopes
            are not satisfied.
    """
    if token_data is None:
        return None

    return await get_user_by_id_dependency(
        token_data.uid,  # type: ignore
        session,
        user_repo,
    )
