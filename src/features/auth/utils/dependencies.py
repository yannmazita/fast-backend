# src/features/auth/utils/dependencies
import structlog
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, SecurityScopes
import jwt
from jwt.exceptions import PyJWTError
from pydantic import ValidationError

from src.core.exceptions import PermissionDenied
from src.common.utils.settings import settings
from src.features.auth.schemas import TokenData
from src.features.auth.utils.scopes import OAUTH_SCOPES

logger = structlog.get_logger(__name__)

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login",
    scopes=OAUTH_SCOPES,
    auto_error=False,
)


async def validate_token(
    security_scopes: SecurityScopes,
    token: Annotated[str | None, Depends(oauth2_scheme)],
) -> TokenData:
    """
    Validates JWT token, extracts claims, and checks token-level scopes.
    Does NOT perform comprehensive user status checks (active, banned, disabled) here.
    Those checks are delegated to other dependencies like `get_current_active_user`
    or service layers that use the user ID/username from this token data.
    """
    if token is None:
        # This case might be hit if oauth2_scheme is called on an optional token,
        # but for Security() wrapped dependencies, FastAPI usually handles missing token earlier
        # if auto_error=True. Since it's False, this check is important.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    authenticate_value = (
        f'Bearer scope="{security_scopes.scope_str}"'
        if security_scopes.scopes
        else "Bearer"
    )

    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
        username: str | None = payload.get("sub")
        user_id_str: str | None = payload.get("uid")

        if username is None or user_id_str is None:
            logger.warning("Token missing username or uid.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing username or user ID.",
                headers={"WWW-Authenticate": authenticate_value},
            )

        try:
            # Pydantic can't parse UUID from a string in a dict spread,
            # so we handle it before instantiation.
            payload["uid"] = UUID(user_id_str)
        except ValueError:
            logger.warning(f"Token contains invalid UUID format for uid: {user_id_str}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: user ID format is incorrect.",
                headers={"WWW-Authenticate": authenticate_value},
            )

        # Let Pydantic instantiate the model from the payload.
        # It will validate all fields and ignore extras like 'exp'.
        token_data = TokenData(**payload)

    except (
        PyJWTError
    ) as e:  # CatchesExpiredSignatureError, ImmatureSignatureError, etc.
        logger.warning(f"PyJWTError during token decoding: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials: invalid token.",  # Keep generic for security
            headers={"WWW-Authenticate": authenticate_value},
        ) from e
    except ValidationError as e:  # If TokenData instantiation fails
        logger.warning(f"TokenData ValidationError: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials: token data malformed.",
            headers={"WWW-Authenticate": authenticate_value},
        ) from e

    # Scope checking:
    # The token must contain ALL scopes required by the endpoint.
    # Access for administrators is now handled by ensuring their role (ROLE_ADMINISTRATOR)
    # is mapped to all necessary granular scopes, which are then included in their token
    # by AuthService.create_access_token.

    required_scopes_set = set(security_scopes.scopes)
    # token_data.scopes should already be a list of strings from TokenData model
    token_scopes_set = set(token_data.scopes)

    if not required_scopes_set.issubset(token_scopes_set):
        logger.warning(
            f"Permission denied for sub '{token_data.sub}' (UID: {token_data.uid}). "
            f"Required scopes: {required_scopes_set}, Token scopes: {token_scopes_set}."
        )
        raise PermissionDenied(
            detail=f"Not enough permissions. Requires scopes: {security_scopes.scope_str}",
            # headers={"WWW-Authenticate": authenticate_value} # Typically 403 doesn't need WWW-Authenticate
        )

    return token_data
