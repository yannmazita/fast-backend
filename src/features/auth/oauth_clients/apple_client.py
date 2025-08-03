# src/features/auth/oauth_clients/apple_client
import structlog
import httpx
import asyncio
from authlib.integrations.httpx_client import AsyncOAuth2Client
from authlib.oauth2.rfc6749.errors import OAuth2Error
from authlib.jose import JsonWebKey
from authlib.oidc.core import UserInfo

from src.common.utils.settings import settings
from src.core.exceptions import AppException, InvalidCredentials

logger = structlog.get_logger(__name__)

# Apple uses OIDC, so "openid" is mandatory for ID token parsing
APPLE_SCOPES = ["openid", "email", "name"]

apple_oauth_client_instance: AsyncOAuth2Client | None = None
_init_lock = asyncio.Lock()


async def get_apple_oauth_client() -> AsyncOAuth2Client:
    global apple_oauth_client_instance
    if apple_oauth_client_instance is None:
        async with _init_lock:
            # Double-check pattern for thread safety
            if apple_oauth_client_instance is None:
                if (
                    not settings.apple_client_id
                    or not settings.apple_team_id
                    or not settings.apple_key_id
                    or not settings.apple_private_key
                ):
                    logger.error("Apple OAuth client core settings are incomplete.")
                    raise AppException(
                        "Apple OAuth is not configured properly (core settings)."
                    )

                if not settings.apple_redirect_uri:  # New check
                    logger.error("Apple OAuth redirect URI not configured in settings.")
                    raise AppException("Apple OAuth redirect URI is missing.")

                key = JsonWebKey.import_key(
                    settings.apple_private_key, {"kty": "EC"}
                )

                client = AsyncOAuth2Client(
                    client_id=settings.apple_client_id,
                    scope=" ".join(APPLE_SCOPES),
                    redirect_uri=settings.apple_redirect_uri,
                    token_endpoint_auth_method="client_secret_jwt",
                    client_auth_kwargs={
                        "key": key,
                        "token_endpoint": "https://appleid.apple.com/auth/token",
                        "claims": {
                            "iss": settings.apple_team_id,
                            "sub": settings.apple_client_id,
                            "aud": "https://appleid.apple.com",
                        },
                        "header": {
                            "kid": settings.apple_key_id,
                            "alg": "ES256",
                        },
                    },
                    server_metadata_url="https://appleid.apple.com/.well-known/openid-configuration",
                )
                apple_oauth_client_instance = client
    return apple_oauth_client_instance


async def generate_apple_auth_redirect(
    redirect_uri: str, state: str
) -> tuple[str, str]:
    client = await get_apple_oauth_client()
    auth_url, _ = client.create_authorization_url(
        url=None,  # Authlib will use server_metadata_url to find the authorization_endpoint
        state=state,
        redirect_uri=redirect_uri,
        response_mode="form_post",  # Required by Apple for web apps
    )
    return auth_url, state


async def exchange_apple_code_for_token_and_userinfo(
    code: str, redirect_uri: str
) -> dict:
    client = await get_apple_oauth_client()  # Changed to await

    token_data = await client.fetch_token(  # type: ignore
        url=None,  # Authlib will use server_metadata_url to find the token_endpoint
        code=code,
        redirect_uri=redirect_uri,  # This redirect_uri must match the one used in the auth request
    )

    # For OIDC, userinfo is in the ID token.
    # parse_id_token also validates the token (signature, aud, exp, etc.)
    # It expects the full token response dictionary which includes 'id_token'.
    user_claims: UserInfo | None = client.parse_id_token(token_data)  # type: ignore

    if not user_claims:
        # This case should ideally not be reached if id_token is present and valid
        logger.error("Failed to parse Apple ID token or ID token is empty.")
        raise InvalidCredentials("Could not parse user information from Apple.")

    if not user_claims.get("sub"):
        logger.error(f"Apple ID token missing 'sub' claim: {user_claims}")
        raise InvalidCredentials(
            "Apple user information is incomplete (missing subject)."
        )

    # Apple may include name and email in the ID token only on the first authentication.
    # If 'email' or 'name' scopes were requested, check for them.
    # However, their absence might not always be an error if they were not provided by Apple.
    # For now, we just ensure 'sub' is present.

    return dict(user_claims)
