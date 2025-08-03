# src/features/users/utils/management.py
import structlog

from sqlalchemy.ext.asyncio.session import AsyncSession

from src.common.database import sessionmanager
from src.common.utils.settings import settings
from src.core.exceptions import DuplicateResource, ResourceNotFound
from src.features.auth.utils.scopes import UserRoles
from src.features.users.models import User
from src.features.users.repository import BanRepository, UserRepository
from src.features.users.schemas import UserCreate
from src.features.users.services.users import UserService

logger = structlog.get_logger(__name__)


async def _ensure_user_with_roles(
    session: AsyncSession,
    user_service: UserService,
    username: str,
    password: str,
    email: str | None,
    target_roles: str,
    is_super_user: bool = False,
):
    user_repo = user_service.user_repository
    try:
        logger.info(
            f"Attempting to create/update user '{username}' with roles '{target_roles}'."
        )
        user_create_data = UserCreate(
            username=username,
            password=password,
            confirm_password=password,
            email=email,
            roles=target_roles,
        )
        user: User = await user_repo.create(session, user_create_data)
        await session.commit()
        await session.refresh(user)
        logger.info(
            f"User '{username}' created with ID: {user.id} and roles: '{user.roles}'."
        )
    except DuplicateResource:
        logger.info(
            f"User '{username}' already exists. Ensuring roles are correctly set."
        )
        try:
            existing_user = await user_repo.get_by_attribute(
                session, username, "username"
            )

            current_roles_set = set((existing_user.roles or "").split())
            # Ensure target_roles is split correctly, even if it's a single role without spaces
            target_roles_set = set(target_roles.split())

            # Check if all target roles are already present.
            if not target_roles_set.issubset(current_roles_set):
                new_roles_str = target_roles

                logger.info(
                    f"User '{username}' (ID: {existing_user.id}) found. Updating roles from '{existing_user.roles}' to '{new_roles_str}'."
                )
                await user_service.update_roles(
                    session=session,
                    user_id=existing_user.id,
                    new_roles=new_roles_str,
                )
                logger.info(
                    f"Roles updated for existing user '{username}' (ID: {existing_user.id})."
                )
            else:
                logger.info(
                    f"Existing user '{username}' already has the target roles '{target_roles}' or a superset."
                )

            # Ensure superuser (or any user marked by is_super_user flag) is active
            if is_super_user and not existing_user.is_active:
                logger.info(
                    f"Activating existing user '{username}' marked as super_user/is_ensure_active."
                )
                await user_service.update_user_active_status(
                    session, existing_user.id, True
                )

        except ResourceNotFound:
            logger.error(
                f"User '{username}' was reported as duplicate but not found. This indicates an inconsistent state."
            )


async def create_superuser():
    """Creates or updates the superuser defined in settings."""
    async with sessionmanager.session() as session:
        user_repository = UserRepository()
        ban_repository = BanRepository()
        user_service = UserService(
            user_repository=user_repository,
            ban_repository=ban_repository,
        )

        superuser_roles = f"{UserRoles.ADMINISTRATOR.value} {UserRoles.REGULAR.value}"
        await _ensure_user_with_roles(
            session=session,
            user_service=user_service,
            username=settings.admin_username,
            password=settings.admin_password,
            email=settings.admin_email,
            target_roles=superuser_roles,
            is_super_user=True,
        )
        logger.info(
            f"Superuser '{settings.admin_username}' creation/update process completed."
        )
