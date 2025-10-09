# src/features/auth/repository
import structlog
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.common.repository import DatabaseRepository
from src.core.exceptions import AppException, ResourceNotFound
from src.features.auth.models import OAuthAccount, RefreshToken
from src.features.auth.schemas import OAuthAccountCreate

logger = structlog.get_logger(__name__)


class OAuthAccountRepository(DatabaseRepository):
    """Repository for database operations on OAuthAccount models."""

    def __init__(self):
        super().__init__(OAuthAccount)

    async def get_by_provider(
        self, session: AsyncSession, oauth_name: str, provider_user_id: str
    ) -> OAuthAccount:  # Return type is OAuthAccount, raises ResourceNotFound
        """Retrieves an OAuth account by provider and provider-specific user ID.

        This method eagerly loads the associated User object.

        Args:
            session: The database session.
            oauth_name: The name of the OAuth provider (e.g., "google").
            provider_user_id: The user's unique ID from that provider.

        Returns:
            The found OAuthAccount instance with its related User loaded.

        Raises:
            ResourceNotFound: If no matching OAuth account is found.
        """
        query = (
            select(self.model)
            .where(
                self.model.oauth_name == oauth_name,
                self.model.provider_user_id == provider_user_id,
            )
            .options(
                selectinload(self.model.user)
            )  # Eagerly load the 'user' relationship
        )
        response = await session.execute(query)
        instance = response.scalar_one_or_none()
        if not instance:
            raise ResourceNotFound(
                f"OAuthAccount for provider '{oauth_name}' not found."
            )
        return instance

    async def create_oauth_account(
        self, session: AsyncSession, data: OAuthAccountCreate, user_id: UUID
    ) -> OAuthAccount:
        """Creates a new OAuthAccount and links it to an existing user.

        Args:
            session: The database session.
            data: The schema containing the new OAuth account details.
            user_id: The UUID of the user to link this account to.

        Returns:
            The newly created OAuthAccount instance.
        """
        oauth_account_data = data.model_dump()
        oauth_account_data["user_id"] = user_id
        return await super().create_and_commit(session, oauth_account_data)


class RefreshTokenRepository(DatabaseRepository):
    """Repository for database operations on RefreshToken models."""

    def __init__(self):
        super().__init__(RefreshToken)

    async def get_by_jti(self, session: AsyncSession, jti: str) -> RefreshToken:
        """Retrieves a refresh token by its JTI (JWT ID).

        Args:
            session: The database session.
            jti: The JTI (unique identifier) of the token.

        Returns:
            The found RefreshToken instance.

        Raises:
            ResourceNotFound: If no token with the given JTI is found.
        """
        return await self.get_by_attribute(session, jti, "jti")

    async def create_token(
        self, session: AsyncSession, user_id: UUID, jti: str, expires_at: datetime
    ) -> RefreshToken:
        """Creates a new refresh token record in the database.

        Args:
            session: The database session.
            user_id: The UUID of the user who owns the token.
            jti: The JTI (unique identifier) of the token.
            expires_at: The expiration timestamp of the token.

        Returns:
            The newly created RefreshToken instance.
        """
        token_data = {
            "user_id": user_id,
            "jti": jti,
            "expires_at": expires_at,
        }
        return await self.create_and_commit(session, token_data)

    async def revoke_token(self, session: AsyncSession, jti: str) -> RefreshToken:
        """Revokes a refresh token by setting its `revoked_at` timestamp.

        This action is idempotent; revoking an already-revoked token will
        not raise an error.

        Args:
            session: The database session.
            jti: The JTI of the token to revoke.

        Returns:
            The updated (revoked) RefreshToken instance.
        """
        token = await self.get_by_jti(session, jti)
        if token.revoked_at:
            logger.warning(f"Attempted to revoke an already revoked token: jti={jti}")
            return token  # Idempotent

        update_data = {"revoked_at": datetime.now(timezone.utc)}
        return await self.update_by_attribute(session, update_data, jti, "jti")
