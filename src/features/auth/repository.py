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
    def __init__(self):
        super().__init__(OAuthAccount)

    async def get_by_provider(
        self, session: AsyncSession, oauth_name: str, provider_user_id: str
    ) -> OAuthAccount:  # Return type is OAuthAccount, raises ResourceNotFound
        """
        Get an OAuthAccount by provider name and provider user ID.
        Eagerly loads the related User.
        Returns the instance or raises ResourceNotFound.
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
        """
        Creates an OAuthAccount record and links it to a user.
        """
        oauth_account_data = data.model_dump()
        oauth_account_data["user_id"] = user_id
        return await super().create_and_commit(session, oauth_account_data)


class RefreshTokenRepository(DatabaseRepository):
    def __init__(self):
        super().__init__(RefreshToken)

    async def get_by_jti(self, session: AsyncSession, jti: str) -> RefreshToken:
        """
        Get a RefreshToken by its JTI (JWT ID).
        Raises ResourceNotFound if not found.
        """
        return await self.get_by_attribute(session, jti, "jti")

    async def create_token(
        self, session: AsyncSession, user_id: UUID, jti: str, expires_at: datetime
    ) -> RefreshToken:
        """
        Creates a new RefreshToken record.
        """
        token_data = {
            "user_id": user_id,
            "jti": jti,
            "expires_at": expires_at,
        }
        return await self.create_and_commit(session, token_data)

    async def revoke_token(self, session: AsyncSession, jti: str) -> RefreshToken:
        """
        Revokes a refresh token by setting its revoked_at timestamp.
        """
        token = await self.get_by_jti(session, jti)
        if token.revoked_at:
            logger.warning(f"Attempted to revoke an already revoked token: jti={jti}")
            return token  # Idempotent

        update_data = {"revoked_at": datetime.now(timezone.utc)}
        return await self.update_by_attribute(session, update_data, jti, "jti")
