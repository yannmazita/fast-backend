# src.features.users.repository
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio.session import AsyncSession

from src.common.repository import DatabaseRepository
from src.features.auth.utils.password import get_password_hash
from src.features.users.models import User, Ban
from src.features.users.schemas import (
    UserCreate,
)


class UserRepository(DatabaseRepository):
    """
    Repository for performing database queries on users.
    """

    def __init__(self):
        super().__init__(User)

    async def create(self, session: AsyncSession, data: UserCreate | dict) -> User:
        """Creates a user, hashing the password if provided."""
        create_data = data if isinstance(data, dict) else data.model_dump()

        # Remove confirmation password if it exists, as it's not part of the User model
        create_data.pop("confirm_password", None)

        if "password" in create_data and create_data["password"]:
            create_data["password"] = get_password_hash(create_data["password"])

        # The parent's `create` method expects the password to be in `hashed_password`
        if "password" in create_data:
            create_data["hashed_password"] = create_data.pop("password")

        return await super().create(session, create_data)

    async def get_guest_by_ip(self, session: AsyncSession, ip_address: str) -> User:
        """Retrieves a guest user by their IP address."""
        return await self.get_by_attribute(session, ip_address, "ip_address")


class BanRepository(DatabaseRepository):
    """
    Repository for performing database queries on bans.
    """

    def __init__(self):
        super().__init__(Ban)

    async def get_active_ban_by_user_id(
        self, session: AsyncSession, user_id: UUID
    ) -> Ban | None:
        """
        Retrieves the currently active ban for a given user, if any.
        An active ban is one that is_currently_active = True and
        (expires_at is NULL OR expires_at > now).
        If multiple such bans exist (which should ideally not happen if logic is correct),
        the one most recently banned_at is returned.
        """
        stmt = (
            select(Ban)
            .where(
                Ban.user_id == user_id,
                Ban.is_currently_active,
                or_(
                    Ban.expires_at.is_(None),
                    Ban.expires_at > datetime.now(timezone.utc),
                ),
            )
            .order_by(Ban.banned_at.desc())
        )
        result = await session.execute(stmt)
        return result.scalars().first()

    async def get_ban_history_by_user_id(
        self, session: AsyncSession, user_id: UUID, offset: int = 0, limit: int = 100
    ) -> tuple[list[Ban], int]:
        """
        Retrieves the ban history for a given user, paginated.
        Returns a list of Ban objects and the total count of bans for that user.
        """
        count_stmt = (
            select(func.count(Ban.id)).select_from(Ban).where(Ban.user_id == user_id)
        )
        total_count_res = await session.execute(count_stmt)
        total_count = total_count_res.scalar_one()

        if total_count == 0:
            return [], 0

        stmt = (
            select(Ban)
            .where(Ban.user_id == user_id)
            .order_by(Ban.banned_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await session.execute(stmt)
        bans = result.scalars().all()
        return list(bans), total_count
