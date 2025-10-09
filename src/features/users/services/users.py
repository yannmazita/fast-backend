# src.features.users.services.users
import structlog
from typing import Annotated
from uuid import UUID
from datetime import datetime, timedelta, timezone

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import InvalidCredentials, UserDisabledError, BadRequestError
from src.features.auth.schemas import OAuthAccountRead
from src.features.auth.utils.password import get_password_hash, verify_password
from src.features.users.models import User, Ban
from src.features.users.repository import UserRepository, BanRepository
from src.features.users.schemas import (
    BanCreate,
    BanRead,
    UserCreate,
    UserRead,
)
from src.features.users.utils.export_schemas import UserDataExport

logger = structlog.get_logger(__name__)

USER_SELF_DISABLE_PERIOD_DAYS = 30
MAX_RECORDS_FOR_EXPORT = 1000


class UserService:
    """
    Class for user-related operations, including disabling, banning.
    """

    def __init__(
        self,
        user_repository: Annotated[UserRepository, Depends()],
        ban_repository: Annotated[BanRepository, Depends()],
    ):
        self.user_repository = user_repository
        self.ban_repository = ban_repository

    async def create_user(self, session: AsyncSession, user_data: UserCreate) -> User:
        """Creates a new user."""
        return await self.user_repository.create_and_commit(
            session, user_data.model_dump()
        )

    async def update_password(
        self,
        session: AsyncSession,
        user_id: UUID,
        old_password: str | None,
        new_password: str,
    ) -> User:
        """
        Updates a user's password.
        If the user has no password set (like  OAuth user setting one for the first time),
        old_password is not required. Otherwise, it's verified.
        """
        logger.debug(f"Attempting password update for user ID: {user_id}")
        user = await self.user_repository.get_by_attribute(
            session,
            user_id,
            "id",
            with_for_update=False,  # Read without lock first
        )

        if user.hashed_password:  # User has an existing password
            if not old_password:
                raise BadRequestError(
                    "Old password is required to change an existing password."
                )
            if not verify_password(old_password, user.hashed_password):
                logger.warning(
                    f"Incorrect old password provided for user ID: {user_id}"
                )
                raise InvalidCredentials("Incorrect old password provided.")
        elif old_password:  # User has no password, but old_password was provided
            raise BadRequestError(
                "Old password should not be provided when setting a password for the first time."
            )

        hashed_new_password = get_password_hash(new_password)
        update_data = {"hashed_password": hashed_new_password}

        # Re-fetch with lock for update
        # Note: This simple re-fetch might not be strictly necessary if the initial get_by_attribute
        # was already for update, but separating read and write phases can be clearer.
        # For this operation, updating a single field, it's generally safe.
        # A more robust approach for complex multi-step updates might involve a single locked fetch.
        updated_user = await self.user_repository.update_by_attribute(
            session, update_data, user_id, "id"
        )
        logger.debug(f"Password updated successfully for user ID: {user_id}")
        return updated_user

    async def update_username(
        self, session: AsyncSession, user_id: UUID, new_username: str
    ) -> User:
        logger.debug(f"Attempting username update for user ID: {user_id}")
        update_data = {"username": new_username}
        updated_user = await self.user_repository.update_by_attribute(
            session, update_data, user_id, "id"
        )
        logger.debug(
            f"Username updated successfully for user ID: {user_id} to '{new_username}'"
        )
        return updated_user

    async def update_roles(
        self, session: AsyncSession, user_id: UUID, new_roles: str
    ) -> User:
        logger.debug(f"Attempting roles update for user ID: {user_id}")
        update_data = {"roles": new_roles}
        updated_user = await self.user_repository.update_by_attribute(
            session, update_data, user_id, "id"
        )
        logger.debug(
            f"Roles updated successfully for user ID: {user_id} to '{new_roles}'"
        )
        return updated_user

    async def update_user_active_status(
        self, session: AsyncSession, user_id: UUID, is_active: bool
    ) -> User:
        """Updates the is_active status of a user (admin action)."""
        logger.debug(f"Attempting to set is_active={is_active} for user ID: {user_id}")
        update_data = {"is_active": is_active}
        updated_user = await self.user_repository.update_by_attribute(
            session, update_data, user_id, "id"
        )
        logger.info(f"User ID: {user_id} is_active status set to {is_active}")
        return updated_user

    async def get_all_users(
        self, session: AsyncSession, offset: int = 0, limit: int = 100
    ):
        """Retrieves all users with pagination."""
        return await self.user_repository.get_all(session, offset, limit)

    async def disable_account(self, session: AsyncSession, user_id: UUID) -> User:
        """User self-disables their account."""
        logger.info(f"User ID: {user_id} is attempting to self-disable account.")
        user = await self.user_repository.get_by_attribute(session, user_id, "id")
        if user.disabled_at:
            raise BadRequestError("Account is already disabled.")

        update_data = {"disabled_at": datetime.now(timezone.utc)}
        updated_user = await self.user_repository.update_by_attribute(
            session, update_data, user_id, "id"
        )
        logger.info(f"User ID: {user_id} has self-disabled their account.")
        return updated_user

    async def enable_account(self, session: AsyncSession, user_id: UUID) -> User:
        """User re-enables their account by logging in within the grace period."""
        logger.info(f"User ID: {user_id} is being re-enabled.")
        # This method assumes checks for grace period have already passed.
        update_data = {"disabled_at": None}
        updated_user = await self.user_repository.update_by_attribute(
            session, update_data, user_id, "id", none_replace=True
        )
        logger.debug(f"User ID: {user_id} has been re-enabled.")
        return updated_user

    async def check_and_handle_disabled_status(
        self, session: AsyncSession, user: User
    ) -> User:
        """
        Checks if a user account is self-disabled and handles re-activation or permanent disable error.
        Returns the user, potentially re-enabled.
        """
        if user.disabled_at:
            logger.debug(f"User ID: {user.id} has disabled_at set: {user.disabled_at}")
            grace_period_end = user.disabled_at + timedelta(
                days=USER_SELF_DISABLE_PERIOD_DAYS
            )
            if datetime.now(timezone.utc) > grace_period_end:
                logger.warning(
                    f"User ID: {user.id} self-disable period expired. Account is permanently disabled."
                )
                # await self.update_user_active_status(session, user.id, False)
                raise UserDisabledError(permanently_disabled=True)
            else:
                logger.info(
                    f"User ID: {user.id} re-activating account within grace period."
                )
                return await self.enable_account(session, user.id)
        return user

    async def create_ban(
        self, session: AsyncSession, ban_data: BanCreate, admin_user_id: UUID | None
    ) -> Ban:
        """Creates a new ban for a user."""
        logger.info(
            f"Attempting to ban user ID: {ban_data.user_id} by admin ID: {admin_user_id}"
        )
        # Ensure user exists before trying to ban
        await self.user_repository.get_by_attribute(session, ban_data.user_id, "id")

        # Check if there's already an active ban
        existing_active_ban = await self.ban_repository.get_active_ban_by_user_id(
            session, ban_data.user_id
        )
        if existing_active_ban:
            logger.warning(
                f"User ID: {ban_data.user_id} already has an active ban (ID: {existing_active_ban.id})."
            )
            raise BadRequestError(
                f"User already has an active ban. Deactivate the existing ban (ID: {existing_active_ban.id}) before creating a new one."
            )

        ban_dict = ban_data.model_dump()
        ban_dict["banned_by_id"] = admin_user_id
        ban_dict["is_currently_active"] = True  # New bans are active by default

        new_ban = await self.ban_repository.create_and_commit(session, ban_dict)
        logger.info(
            f"User ID: {ban_data.user_id} banned successfully. Ban ID: {new_ban.id}"
        )
        return new_ban

    async def deactivate_ban(
        self,
        session: AsyncSession,
        ban_id: UUID,
        admin_user_id: UUID | None,  # admin_user_id for audit purposes
    ) -> Ban:
        """Deactivates an existing ban."""
        logger.info(
            f"Attempting to deactivate ban ID: {ban_id} by admin ID: {admin_user_id}"
        )
        # BanRepository.update_by_attribute will raise ResourceNotFound if ban_id is invalid
        update_data = {
            "is_currently_active": False,
            "deactivated_at": datetime.now(timezone.utc),
            "deactivated_by_id": admin_user_id,
        }
        updated_ban = await self.ban_repository.update_by_attribute(
            session, update_data, ban_id, "id"
        )
        logger.info(
            f"Ban ID: {ban_id} deactivated successfully by admin ID: {admin_user_id}."
        )
        return updated_ban

    async def get_user_ban_history(
        self, session: AsyncSession, user_id: UUID, offset: int = 0, limit: int = 100
    ) -> tuple[list[Ban], int]:
        """Retrieves the ban history for a user."""
        logger.debug(f"Fetching ban history for user ID: {user_id}")
        # Ensure user exists
        await self.user_repository.get_by_attribute(session, user_id, "id")

        bans, total_count = await self.ban_repository.get_ban_history_by_user_id(
            session, user_id, offset, limit
        )
        return bans, total_count

    async def _export_profile_data(self, session: AsyncSession, user: User) -> UserRead:
        """Exports the user's profile data."""

        return UserRead(
            id=user.id,  # type: ignore
            username=user.username,
            email=user.email,
            roles=user.roles,
            is_active=user.is_active,
            is_guest=user.is_guest,
            disabled_at=user.disabled_at,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

    def _export_oauth_accounts(self, user: User) -> list[OAuthAccountRead]:
        """Exports the user's OAuth accounts."""
        oauth_accounts_data = [
            OAuthAccountRead.model_validate(oa) for oa in user.oauth_accounts
        ]
        logger.debug(
            f"Fetched {len(oauth_accounts_data)} OAuth accounts for user {user.id}"
        )
        return oauth_accounts_data

    async def _export_ban_history(
        self, session: AsyncSession, user_id: UUID
    ) -> list[BanRead]:
        """Exports the user's ban history."""
        raw_bans, total_bans = await self.ban_repository.get_ban_history_by_user_id(
            session, user_id, offset=0, limit=MAX_RECORDS_FOR_EXPORT
        )
        if total_bans > MAX_RECORDS_FOR_EXPORT:
            logger.warning(
                f"User {user_id} has {total_bans} bans, but only {MAX_RECORDS_FOR_EXPORT} were fetched for export. Consider implementing full pagination."
            )
        ban_history_data = [BanRead.model_validate(b) for b in raw_bans]
        logger.debug(f"Fetched {len(ban_history_data)} ban records for user {user_id}")
        return ban_history_data

    async def export_user_data(
        self, session: AsyncSession, user: User
    ) -> UserDataExport:
        """
        Aggregates all personal data for the given user for GDPR export.
        """
        logger.info(f"Starting data export for user ID: {user.id}")

        # 1. Profile Data
        user_data = await self._export_profile_data(session, user)

        # 2. OAuth Accounts
        oauth_accounts_data = self._export_oauth_accounts(user)

        # 3. Ban History
        ban_history_data = await self._export_ban_history(session, user.id)

        # 4. Assemble UserDataExport
        user_data_export_obj = UserDataExport(
            profile=user_data,
            oauth_accounts=oauth_accounts_data,
            ban_history=ban_history_data,
        )

        logger.info(f"Data export prepared successfully for user ID: {user.id}")
        return user_data_export_obj
