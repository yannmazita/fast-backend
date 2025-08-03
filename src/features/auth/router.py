# src.features.auth.router
from typing import Annotated

import structlog
from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from fastapi.exceptions import HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.database import get_session
from src.common.utils.settings import settings
from src.features.auth.oauth_router import oauth_router
from src.features.auth.schemas import (
    Token,
)
from src.features.auth.services.authentication import AuthService
from src.features.auth.utils.cookie import (
    clear_refresh_token_cookie,
    set_refresh_token_cookie,
)


logger = structlog.get_logger(__name__)

router = APIRouter(tags=["auth"], prefix="/auth")

router.include_router(oauth_router)


@router.post("/login", response_model=Token)
async def internal_login(
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[AsyncSession, Depends(get_session)],
    auth_service: Annotated[AuthService, Depends()],
):
    """
    Logs in a user with an internal account (username and password).
    Returns an access token in the body and sets the refresh token in an HttpOnly cookie.
    """
    token_details = await auth_service.get_access_token(
        session,
        scopes=form_data.scopes,
        username=form_data.username,
        password=form_data.password,
    )
    set_refresh_token_cookie(response, token_details.refresh_token)
    return Token(
        access_token=token_details.access_token,
        token_type=token_details.token_type,
        expires_at=token_details.expires_at,
    )


@router.post(
    "/guest-login",
    response_model=Token,
    status_code=status.HTTP_201_CREATED,
)
async def guest_login(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    auth_service: Annotated[AuthService, Depends()],
):
    """
    Logs in a user as a guest. The refresh token is set in an HttpOnly cookie.
    """
    client_ip = request.client.host
    _, token_details = await auth_service.login_as_guest(session, client_ip)
    set_refresh_token_cookie(response, token_details.refresh_token)
    return Token(
        access_token=token_details.access_token,
        token_type=token_details.token_type,
        expires_at=token_details.expires_at,
    )


@router.post("/refresh", response_model=Token)
async def refresh_token_endpoint(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    auth_service: Annotated[AuthService, Depends()],
    refresh_token: Annotated[
        str | None, Cookie(alias=settings.refresh_token_cookie_name)
    ] = None,
):
    """
    Refreshes an access token using the refresh token from the HttpOnly cookie.
    Returns a new access token and sets a new rotated refresh token in the cookie.
    """
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found.",
        )

    new_token_details = await auth_service.refresh_access_token(session, refresh_token)
    set_refresh_token_cookie(response, new_token_details.refresh_token)

    return Token(
        access_token=new_token_details.access_token,
        token_type=new_token_details.token_type,
        expires_at=new_token_details.expires_at,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_endpoint(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    auth_service: Annotated[AuthService, Depends()],
    refresh_token: Annotated[
        str | None, Cookie(alias=settings.refresh_token_cookie_name)
    ] = None,
):
    """
    Logs out the user by revoking the refresh token and clearing the cookie.
    """
    if refresh_token:
        await auth_service.revoke_refresh_token(session, refresh_token)

    clear_refresh_token_cookie(response)
    return


#
# Internal user registration is disabled as it is not complete.
# Completing the flow requires email verification.
# Todo: pay for emails
#
# @router.post("/register", response_model=UserRead)
# async def internal_registration(
#    user_data: UserCreate,
#    session: Annotated[AsyncSession, Depends(get_session)],
#    user_repo: Annotated[UserRepository, Depends()],
# ):
#    if not user_data.password:
#        raise HTTPException(
#            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
#            detail="Password is required for direct registration.",
#        )
#    new_user_orm = await user_repo.create(session, user_data)
#    return new_user_orm
