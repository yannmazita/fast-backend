# src/features/users/services/cleanup.py
import structlog
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.utils.settings import settings
from src.features.users.models import User

logger = structlog.get_logger(__name__)


class UserCleanupService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_inactive_guest_accounts(self) -> list[User]:
        """
        Retrieves guest accounts that have not been updated within the cleanup period.
        """
        cleanup_threshold = datetime.now(timezone.utc) - timedelta(
            days=settings.guest_account_cleanup_days
        )
        stmt = select(User).where(
            User.is_guest, User.updated_at < cleanup_threshold
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_disabled_accounts_for_cleanup(self) -> list[User]:
        """
        Retrieves non-guest accounts that were disabled longer than the grace period.
        """
        cleanup_threshold = datetime.now(timezone.utc) - timedelta(
            days=settings.disabled_account_cleanup_days
        )
        stmt = select(User).where(
            User.is_guest.is_(False),
            User.is_active.is_(False),
            User.disabled_at < cleanup_threshold,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_inactive_registered_accounts(self) -> list[User]:
        """
        Retrieves registered accounts that have not been updated within the cleanup period.
        """
        cleanup_threshold = datetime.now(timezone.utc) - timedelta(
            days=settings.inactive_registered_account_cleanup_days
        )
        stmt = select(User).where(
            User.is_guest.is_(False),
            User.is_active.is_(True),
            User.updated_at < cleanup_threshold,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_user(self, user: User):
        """
        Permanently deletes a user from the database.
        """
        logger.info(f"Deleting user {user.id} ({user.username}).")
        await self.session.delete(user)
        await self.session.commit()
