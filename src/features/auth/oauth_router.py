# src.features.auth.oauth_router
import secrets
from typing import Annotated
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Form, Request, status, HTTPException, Response
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from src.common.database import get_session
from src.common.utils.settings import settings
from src.core.exceptions import (
    AppException,
    DuplicateResource,
    InvalidCredentials,
    BadRequestError,
)
from src.features.auth.oauth_clients import apple_client, google_client
from src.features.auth.services.authentication import AuthService
from src.features.auth.schemas import (
    CompleteOAuthRegistrationRequest,
    OAuthFlowStatus,
    Token,
)

logger = structlog.getLogger(__name__)

oauth_router = APIRouter(prefix="/oauth")


from src.features.auth.utils.oauth import get_error_redirect_response
from src.features.auth.utils.cookie import set_refresh_token_cookie


def _set_oauth_state_cookie(response: JSONResponse | RedirectResponse, state: str):
    response.set_cookie(
        key=settings.oauth_state_cookie_name,
        value=state,
        max_age=settings.oauth_state_expire_minutes * 60,
        httponly=True,
        samesite="lax",
        secure=settings.environment != "DEV",
    )


def _clear_oauth_state_cookie(response: JSONResponse | RedirectResponse):
    response.delete_cookie(
        key=settings.oauth_state_cookie_name,
        httponly=True,
        samesite="lax",
        secure=settings.environment != "DEV",
    )


@oauth_router.get("/google/login", name="oauth:google_login")
async def oauth_google_login(request: Request):
    """
    Initiates the Google OAuth2 login flow by redirecting the user to Google's authentication page.
    """
    error_redirect_url_base = str(settings.frontend_error_redirect_uri)

    if not settings.google_client_id:
        logger.error("Google OAuth is not configured (client ID missing).")
        error_message = quote_plus("Google OAuth is not available at the moment.")
        return RedirectResponse(url=f"{error_redirect_url_base}?error={error_message}")

    state = secrets.token_urlsafe(32)

    try:
        auth_url, _ = await google_client.generate_google_auth_redirect(
            redirect_uri_param=str(settings.google_redirect_uri),
            state=state,
        )
    except Exception as e:
        logger.exception("Failed to generate Google auth URL with Authlib.")
        error_message = quote_plus(
            "Could not initiate Google login. Please try again later."
        )
        return RedirectResponse(url=f"{error_redirect_url_base}?error={error_message}")

    response = RedirectResponse(
        url=auth_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT
    )
    _set_oauth_state_cookie(response, state)
    return response


@oauth_router.get("/google/callback", name="oauth:google_callback")
async def oauth_google_callback(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    auth_service: Annotated[AuthService, Depends()],
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    """
    Handles the callback from Google after user authentication.
    Exchanges the authorization code for tokens, retrieves user information,
    and then logs in or proceeds with registration for the user.
    Redirects to the frontend with tokens or a pending registration token.
    """
    error_redirect_url_base = str(settings.frontend_error_redirect_uri)
    success_redirect_url_base = str(settings.frontend_success_redirect_uri)
    complete_registration_redirect_url_base = str(
        settings.frontend_oauth_complete_registration_redirect_uri
    )

    if not settings.google_client_id:
        logger.error("Google OAuth callback hit but Google OAuth is not configured.")
        return get_error_redirect_response("Google OAuth is not available.")

    if error:
        error_description = request.query_params.get(
            "error_description", "Unknown Google error."
        )
        logger.warning(f"Google OAuth error: {error} - {error_description}")
        redirect_response = get_error_redirect_response(
            f"Error from Google: {error_description}"
        )
        _clear_oauth_state_cookie(redirect_response)
        return redirect_response

    stored_state = request.cookies.get(settings.oauth_state_cookie_name)
    if not stored_state or stored_state != state or not code:
        logger.warning(
            f"Invalid state or code in Google callback. Stored: '{stored_state}', Received: '{state}'"
        )
        redirect_response = get_error_redirect_response(
            "Invalid state or missing code from Google."
        )
        _clear_oauth_state_cookie(redirect_response)
        return redirect_response

    try:
        user_info = await google_client.exchange_google_code_for_token_and_userinfo(
            code=code, redirect_uri_param=str(settings.google_redirect_uri)
        )

        provider_user_id = user_info["sub"]
        provider_email = user_info.get("email")
        provider_display_name = user_info.get("name")

        oauth_auth_result = await auth_service.authenticate_via_oauth(
            session,
            provider_name="google",
            provider_user_id=str(provider_user_id),
            provider_email=provider_email,
            provider_display_name=provider_display_name,
        )

        redirect_url: str
        redirect_response: RedirectResponse
        if (
            oauth_auth_result.status == OAuthFlowStatus.USER_AUTHENTICATED
            and oauth_auth_result.user
        ):
            # User authenticated, generate access and refresh tokens
            token_details = await auth_service.get_access_token(
                session,
                scopes=[],
                username=oauth_auth_result.user.username,
                user_object=oauth_auth_result.user,
            )
            redirect_url = (
                f"{success_redirect_url_base}"
                f"#access_token={token_details.access_token}"
                f"&token_type={token_details.token_type}"
                f"&expires_at={quote_plus(token_details.expires_at.isoformat())}"
            )
            redirect_response = RedirectResponse(url=redirect_url)
            set_refresh_token_cookie(redirect_response, token_details.refresh_token)

        elif (
            oauth_auth_result.status == OAuthFlowStatus.USERNAME_REGISTRATION_REQUIRED
            and oauth_auth_result.pending_registration_token
        ):
            # Username registration required
            redirect_url = (
                f"{complete_registration_redirect_url_base}"
                f"#pending_token={oauth_auth_result.pending_registration_token}"
            )
            redirect_response = RedirectResponse(url=redirect_url)
        else:
            logger.error("Invalid OAuthAuthenticationResult state in Google callback.")
            error_message = quote_plus("OAuth processing failed unexpectedly.")
            redirect_url = f"{error_redirect_url_base}?error={error_message}"
            redirect_response = RedirectResponse(url=redirect_url)

        _clear_oauth_state_cookie(redirect_response)
        return redirect_response

    except (AppException, InvalidCredentials, DuplicateResource) as e:
        logger.warning(
            f"Google OAuth callback processing error: {getattr(e, 'detail', str(e))}"
        )
        redirect_response = get_error_redirect_response(
            getattr(e, "detail", "OAuth processing failed")
        )
        _clear_oauth_state_cookie(redirect_response)
        return redirect_response
    except Exception as e:
        logger.exception("Unexpected error in Google OAuth callback.")
        redirect_response = get_error_redirect_response(
            "An unexpected error occurred during Google login"
        )
        _clear_oauth_state_cookie(redirect_response)
        return redirect_response


@oauth_router.get("/apple/login", name="oauth:apple_login")
async def oauth_apple_login(request: Request):
    """
    Initiates the Sign in with Apple OAuth2 login flow by redirecting the user to Apple's authentication page.
    """
    error_redirect_url_base = str(settings.frontend_error_redirect_uri)

    if not settings.apple_client_id:
        logger.error("Apple OAuth is not configured (client ID missing).")
        error_message = quote_plus("Apple OAuth is not available at the moment.")
        return RedirectResponse(url=f"{error_redirect_url_base}?error={error_message}")

    state = secrets.token_urlsafe(32)
    try:
        auth_url, _ = await apple_client.generate_apple_auth_redirect(
            redirect_uri=str(settings.apple_redirect_uri),
            state=state,
        )
    except Exception as e:
        logger.exception("Failed to generate Apple auth URL with Authlib.")
        error_message = quote_plus(
            "Could not initiate Apple login. Please try again later."
        )
        return RedirectResponse(url=f"{error_redirect_url_base}?error={error_message}")

    response = RedirectResponse(
        url=auth_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT
    )
    _set_oauth_state_cookie(response, state)
    return response


@oauth_router.post("/apple/callback", name="oauth:apple_callback")
async def oauth_apple_callback(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    auth_service: Annotated[AuthService, Depends()],
    code: Annotated[str | None, Form()] = None,
    state: Annotated[str | None, Form()] = None,
    user: Annotated[str | None, Form()] = None,  # apple form
    error: Annotated[str | None, Form()] = None,
):
    """
    Handles the callback from Apple after user authentication (via POST).
    Exchanges the authorization code for tokens, retrieves user information,
    and then logs in or proceeds with registration for the user.
    Redirects to the frontend with tokens or a pending registration token.
    Note: Apple sends user name/email info only on the first authorization.
    """
    error_redirect_url_base = str(settings.frontend_error_redirect_uri)
    success_redirect_url_base = str(settings.frontend_success_redirect_uri)
    complete_registration_redirect_url_base = str(
        settings.frontend_oauth_complete_registration_redirect_uri
    )

    if not settings.apple_client_id:
        logger.error("Apple OAuth callback hit but Apple OAuth is not configured.")
        return get_error_redirect_response("Apple OAuth is not available.")

    if error:
        logger.warning(f"Apple OAuth error in callback data: {error}")
        redirect_response = get_error_redirect_response(f"Error from Apple: {error}")
        _clear_oauth_state_cookie(redirect_response)
        return redirect_response

    stored_state = request.cookies.get(settings.oauth_state_cookie_name)
    if not stored_state or stored_state != state or not code:
        logger.warning(
            f"Invalid state or code in Apple callback. Stored: '{stored_state}', Received: '{state}'"
        )
        redirect_response = get_error_redirect_response(
            "Invalid state or missing code from Apple."
        )
        _clear_oauth_state_cookie(redirect_response)
        return redirect_response

    try:
        user_info_claims = (
            await apple_client.exchange_apple_code_for_token_and_userinfo(
                code=code, redirect_uri=str(settings.apple_redirect_uri)
            )
        )

        provider_user_id = user_info_claims["sub"]
        provider_email = user_info_claims.get("email")
        provider_display_name: str | None = None
        if user:  # Apple provides name in a separate 'user' form field on first auth
            try:
                import json

                user_data_from_form = json.loads(user)
                if isinstance(user_data_from_form, dict) and user_data_from_form.get(
                    "name"
                ):
                    name_parts = []
                    if user_data_from_form["name"].get("firstName"):
                        name_parts.append(user_data_from_form["name"]["firstName"])
                    if user_data_from_form["name"].get("lastName"):
                        name_parts.append(user_data_from_form["name"]["lastName"])
                    if name_parts:
                        provider_display_name = " ".join(name_parts)
            except Exception:
                logger.warning(
                    f"Could not parse name from Apple 'user' form field: {user}",
                    exc_info=False,
                )
        if not provider_display_name and user_info_claims.get(
            "name"
        ):  # Fallback if name is in id_token
            provider_display_name = user_info_claims.get("name")

        oauth_auth_result = await auth_service.authenticate_via_oauth(
            session,
            provider_name="apple",
            provider_user_id=str(provider_user_id),
            provider_email=provider_email,
            provider_display_name=provider_display_name,
        )

        redirect_url: str
        redirect_response: RedirectResponse
        if (
            oauth_auth_result.status == OAuthFlowStatus.USER_AUTHENTICATED
            and oauth_auth_result.user
        ):
            token_details = await auth_service.get_access_token(
                session,
                scopes=[],
                username=oauth_auth_result.user.username,
                user_object=oauth_auth_result.user,
            )
            redirect_url = (
                f"{success_redirect_url_base}"
                f"#access_token={token_details.access_token}"
                f"&token_type={token_details.token_type}"
                f"&expires_at={quote_plus(token_details.expires_at.isoformat())}"
            )
            redirect_response = RedirectResponse(url=redirect_url)
            set_refresh_token_cookie(redirect_response, token_details.refresh_token)
        elif (
            oauth_auth_result.status == OAuthFlowStatus.USERNAME_REGISTRATION_REQUIRED
            and oauth_auth_result.pending_registration_token
        ):
            redirect_url = (
                f"{complete_registration_redirect_url_base}"
                f"#pending_token={oauth_auth_result.pending_registration_token}"
            )
            redirect_response = RedirectResponse(url=redirect_url)
        else:
            logger.error("Invalid OAuthAuthenticationResult state in Apple callback.")
            error_message = quote_plus("OAuth processing failed unexpectedly (Apple).")
            redirect_url = f"{error_redirect_url_base}?error={error_message}"
            redirect_response = RedirectResponse(url=redirect_url)

        _clear_oauth_state_cookie(redirect_response)
        return redirect_response

    except (AppException, InvalidCredentials, DuplicateResource) as e:
        logger.warning(
            f"Apple OAuth callback processing error: {getattr(e, 'detail', str(e))}"
        )
        redirect_response = get_error_redirect_response(
            getattr(e, "detail", "OAuth processing failed (Apple)")
        )
        _clear_oauth_state_cookie(redirect_response)
        return redirect_response
    except Exception as e:
        logger.exception("Unexpected error in Apple OAuth callback.")
        redirect_response = get_error_redirect_response(
            "An unexpected error occurred during Apple login."
        )
        _clear_oauth_state_cookie(redirect_response)
        return redirect_response


@oauth_router.post(
    "/complete-registration", response_model=Token, status_code=status.HTTP_201_CREATED
)
async def complete_oauth_registration(
    response: Response,
    registration_data: CompleteOAuthRegistrationRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    auth_service: Annotated[AuthService, Depends()],
):
    """
    Completes the OAuth registration process for a new user.
    This endpoint is used when an OAuth login attempt results in a new user
    who needs to provide a username. It requires a valid pending registration token.
    """
    try:
        result = await auth_service.register_oauth_user(
            session, registration_data.pending_token, registration_data.username
        )
        if result.status == OAuthFlowStatus.USER_AUTHENTICATED and result.user:
            token_details = await auth_service.get_access_token(
                session,
                scopes=[],
                username=result.user.username,
                user_object=result.user,
            )
            set_refresh_token_cookie(response, token_details.refresh_token)
            return Token(
                access_token=token_details.access_token,
                token_type=token_details.token_type,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to complete registration.",
            )
    except (BadRequestError, DuplicateResource) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.detail)
    except InvalidCredentials as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=e.detail)
