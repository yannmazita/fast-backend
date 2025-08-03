# src/features/auth/oauth_clients/google_client.py
from authlib.integrations.httpx_client import AsyncOAuth2Client
from authlib.oauth2.rfc6749.errors import OAuth2Error
import structlog
import httpx
import asyncio

from src.common.utils.settings import settings
from src.core.exceptions import AppException

logger = structlog.get_logger(__name__)

GOOGLE_SCOPES = ["openid", "email", "profile"]

google_oauth_client_instance: AsyncOAuth2Client | None = None
_init_lock = asyncio.Lock()


async def get_google_oauth_client() -> AsyncOAuth2Client:
    global google_oauth_client_instance

    if google_oauth_client_instance is None:
        async with _init_lock:
            # Double-check pattern for thread safety
            if google_oauth_client_instance is None:
                if not settings.google_client_id or not settings.google_client_secret:
                    logger.error("Google OAuth client ID or secret not configured.")
                    raise AppException("Google OAuth is not configured properly.")

                if not settings.google_redirect_uri:
                    logger.error(
                        "Google OAuth redirect URI not configured in settings."
                    )
                    raise AppException("Google OAuth redirect URI is missing.")

                client = AsyncOAuth2Client(
                    client_id=settings.google_client_id,
                    client_secret=settings.google_client_secret,
                    scope=" ".join(GOOGLE_SCOPES),
                    redirect_uri=settings.google_redirect_uri,
                )

                google_oauth_client_instance = client

    return google_oauth_client_instance


async def generate_google_auth_redirect(
    redirect_uri_param: str,
    state: str,
) -> tuple[str, str]:
    client = await get_google_oauth_client()

    auth_url, generated_state = client.create_authorization_url(
        "https://accounts.google.com/o/oauth2/v2/auth",
        state=state,
        redirect_uri=redirect_uri_param,
        access_type="offline",
        prompt="consent",
    )
    return auth_url, state


async def exchange_google_code_for_token_and_userinfo(
    code: str,
    redirect_uri_param: str,
) -> dict:
    # Create a new client instance for this request to avoid state issues
    client = AsyncOAuth2Client(
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        redirect_uri=redirect_uri_param,
    )

    # Fetch the token
    token = await client.fetch_token(  # type: ignore
        "https://oauth2.googleapis.com/token",
        code=code,
        grant_type="authorization_code",
    )

    # Create a new client with the token for authenticated requests
    authenticated_client = AsyncOAuth2Client(
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        token=token,
    )

    # Get userinfo with the authenticated client
    resp = await authenticated_client.get(
        "https://openidconnect.googleapis.com/v1/userinfo"
    )
    resp.raise_for_status()
    user_info = resp.json()

    if not user_info.get("sub") or not user_info.get("email"):
        logger.error(
            f"Google user_info from endpoint missing sub or email: {user_info}"
        )
        raise AppException("Incomplete user info received from Google.")

    return user_info
