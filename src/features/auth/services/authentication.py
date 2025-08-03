# src/features/auth/services/authentication
import structlog
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import uuid4
from random import choice

from fastapi import Depends
import jwt
from jwt.exceptions import PyJWTError
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.utils.settings import settings
from src.core.exceptions import (
    AppException,
    BadRequestError,
    DuplicateResource,
    InvalidCredentials,
    PermissionDenied,
    ResourceNotFound,
    UserBannedError,
    UserDisabledError,
)
from src.features.auth.models import RefreshToken
from src.features.auth.repository import OAuthAccountRepository, RefreshTokenRepository
from src.features.auth.schemas import (
    OAuthAccountCreate,
    OAuthAuthenticationResult,
    OAuthFlowStatus,
    OAuthPendingRegistrationData,
    TokenData,
    TokenFullDetail,
    RefreshTokenData,
)
from src.features.auth.utils.password import verify_password
from src.features.users.models import User
from src.features.users.repository import BanRepository, UserRepository
from src.features.users.schemas import DEFAULT_USER_ROLE, UserCreate
from src.features.users.services.users import UserService

from src.features.auth.utils.role_scope_mapping import (
    get_scopes_for_role_strings,
    ROLE_SCOPES_MAPPING,
)
from src.features.auth.utils.scopes import get_all_defined_scopes, UserRoles

logger = structlog.get_logger(__name__)


class AuthService:
    def __init__(
        self,
        user_repository: Annotated[UserRepository, Depends()],
        ban_repository: Annotated[BanRepository, Depends()],
        user_service: Annotated[UserService, Depends()],
        oauth_account_repository: Annotated[OAuthAccountRepository, Depends()],
        refresh_token_repository: Annotated[RefreshTokenRepository, Depends()],
    ):
        self.user_repository = user_repository
        self.ban_repository = ban_repository
        self.user_service = user_service
        self.oauth_account_repository = oauth_account_repository
        self.refresh_token_repository = refresh_token_repository

    def _create_jwt(
        self,
        token_data: dict,
        expire_delta: timedelta,
    ) -> str:
        """Creates a JWT."""
        expire = datetime.now(timezone.utc) + expire_delta
        to_encode = token_data.copy()
        to_encode["exp"] = int(expire.timestamp())

        encoded_jwt = jwt.encode(
            to_encode, settings.secret_key, algorithm=settings.algorithm
        )
        return encoded_jwt

    async def _create_refresh_token(self, session: AsyncSession, user: User) -> str:
        """Creates a JWT refresh token and stores its metadata in the database."""
        expire_delta = timedelta(minutes=settings.refresh_token_expire_minutes)
        expire = datetime.now(timezone.utc) + expire_delta
        jti = str(uuid4())

        # Persist the token metadata to the database
        await self.refresh_token_repository.create_token(
            session=session, user_id=user.id, jti=jti, expires_at=expire
        )

        token_data = RefreshTokenData(
            sub=user.username,
            uid=user.id,
            jti=jti,
            exp=expire,
        )
        return self._create_jwt(token_data.model_dump(mode="json"), expire_delta)

    def _validate_jwt(self, token: str, purpose: str) -> dict:
        """Validates a JWT and returns its payload."""
        try:
            payload = jwt.decode(
                token, settings.secret_key, algorithms=[settings.algorithm]
            )

            if payload.get("purpose") != purpose:
                raise InvalidCredentials("Invalid token purpose.")

            # Convert exp from timestamp to datetime if it's a timestamp
            if isinstance(payload.get("exp"), (int, float)):
                payload["exp"] = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)

            return payload
        except PyJWTError as e:
            logger.warning(f"JWT validation error: {e}")
            raise InvalidCredentials("Token is invalid or expired.") from e

    async def _validate_refresh_token(
        self, session: AsyncSession, token: str
    ) -> tuple[RefreshToken, User]:
        """
        Validates a refresh token JWT, checks it against the database,
        and returns the database token object and the associated active user.
        """
        payload = self._validate_jwt(token, "refresh")
        token_data = RefreshTokenData(**payload)

        try:
            # Check the database record for the token
            db_token = await self.refresh_token_repository.get_by_jti(
                session, token_data.jti
            )

            if db_token.revoked_at:
                logger.warning(
                    f"Attempt to use a revoked refresh token: jti={db_token.jti}"
                )
                raise InvalidCredentials("Refresh token has been revoked.")

            if db_token.expires_at < datetime.now(timezone.utc):
                logger.warning(
                    f"Attempt to use an expired refresh token: jti={db_token.jti}"
                )
                raise InvalidCredentials("Refresh token has expired.")

            # Fetch and validate the user associated with the token
            user = await self.user_repository.get_by_attribute(
                session, db_token.user_id, "id"
            )
            validated_user = await self._validate_user_status_for_login(session, user)

            return db_token, validated_user

        except ResourceNotFound:
            logger.warning(f"Refresh token jti not found in DB: {token_data.jti}")
            raise InvalidCredentials("Refresh token is invalid.")

    def _create_oauth_pending_registration_token(
        self,
        provider_name: str,
        provider_user_id: str,
        provider_email: str | None,
        provider_display_name: str | None,
    ) -> str:
        """Creates a short-lived JWT for pending OAuth registration."""
        expire_delta = timedelta(
            minutes=settings.oauth_pending_registration_token_expire_minutes
        )
        expire = datetime.now(timezone.utc) + expire_delta

        pending_data = OAuthPendingRegistrationData(
            provider_name=provider_name,
            provider_user_id=provider_user_id,
            provider_email=provider_email,
            provider_display_name=provider_display_name,
            exp=expire,
            # 'purpose' is set by default in the schema
        )
        return self._create_jwt(pending_data.model_dump(), expire_delta)

    def _validate_oauth_pending_registration_token(
        self, token: str
    ) -> OAuthPendingRegistrationData:
        """Validates the pending registration JWT and returns its data."""
        payload = self._validate_jwt(token, "oauth_pending_registration")
        return OAuthPendingRegistrationData(**payload)

    async def _validate_user_status_for_login(
        self, session: AsyncSession, user: User
    ) -> User:
        """
        Centralized method to check user's active status, self-disable status, and bans.
        Raises appropriate exceptions if login should be denied.
        Returns the user object, potentially after re-enabling from self-disable.
        """
        if not user.is_active:
            logger.warning(
                f"Login attempt for disabled user: {user.username} (ID: {user.id})"
            )
            raise UserDisabledError(
                "This account has been disabled. It will be permanently deleted after a grace period."
            )

        if user.is_guest:
            logger.debug(
                f"Guest user '{user.username}' (ID: {user.id}) validation. Skipping self-disable and ban checks."
            )
            return user

        # Following checks apply only to non-guest users
        user = await self.user_service.check_and_handle_disabled_status(session, user)

        active_ban = await self.ban_repository.get_active_ban_by_user_id(
            session, user.id
        )
        if active_ban:
            logger.warning(
                f"Login attempt for banned user: {user.username} (ID: {user.id}). Ban ID: {active_ban.id}"
            )
            raise UserBannedError(
                ban_reason=active_ban.reason, ban_expires_at=active_ban.expires_at
            )
        return user

    async def authenticate_user(
        self, session: AsyncSession, username: str, password: str
    ) -> User:
        """Authenticates a user by username and password, checking active/disabled/banned status."""
        try:
            user: User = await self.user_repository.get_by_attribute(
                session, username, "username"
            )
            user = await self._validate_user_status_for_login(session, user)

            if not user.hashed_password:
                logger.warning(
                    f"Authentication failed: User '{username}' has no password set."
                )
                raise InvalidCredentials(
                    "Account setup via OAuth, no password configured. Please use your OAuth provider to log in or set a password for your account."
                )

            if not verify_password(password, user.hashed_password):
                raise InvalidCredentials()

            logger.debug(f"User {username} has been authenticated successfully.")
            return user
        except ResourceNotFound:
            logger.warning(f"Authentication failed: User '{username}' not found.")
            raise InvalidCredentials()

    async def _get_or_create_user_from_oauth(
        self,
        session: AsyncSession,
        provider_name: str,
        provider_user_id: str,
        provider_email: str | None,
    ) -> User | None:
        try:
            oauth_account = await self.oauth_account_repository.get_by_provider(
                session, provider_name, provider_user_id
            )
            logger.debug(
                f"OAuth account found for {provider_name} ID {provider_user_id}. User ID: {oauth_account.user_id}"
            )
            if (
                not oauth_account.user
            ):  # Should not happen with selectinload and proper data
                logger.error(
                    f"OAuthAccount {oauth_account.id} has no associated user. Data integrity issue."
                )
                raise AppException("OAuth account is orphaned.")
            return oauth_account.user
        except ResourceNotFound:
            logger.debug(
                f"No existing OAuthAccount for {provider_name} ID {provider_user_id}. Will try to link or create user."
            )

        if provider_email:
            try:
                user_to_link = await self.user_repository.get_by_attribute(
                    session, provider_email, "email"
                )
                logger.debug(
                    f"User found by email '{provider_email}' (ID: {user_to_link.id}). Linking OAuth account."
                )
                # Link existing user to this new OAuth account
                oauth_create_data = OAuthAccountCreate(
                    oauth_name=provider_name,
                    provider_user_id=provider_user_id,
                    provider_email=provider_email,
                )
                try:
                    await self.oauth_account_repository.create_oauth_account(
                        session, oauth_create_data, user_to_link.id
                    )
                    logger.debug(
                        f"OAuthAccount for {provider_name} ID {provider_user_id} linked to existing user ID {user_to_link.id}."
                    )
                except (
                    DuplicateResource
                ):  # Should be rare due to initial check, but handle race condition
                    logger.warning(
                        f"OAuthAccount for {provider_name} ID {provider_user_id} already existed when trying to link (race condition likely)."
                    )
                return user_to_link
            except ResourceNotFound:
                logger.debug(
                    f"No existing user found with email '{provider_email}'. New user registration required."
                )
                # Proceed to signal that username input is required

        # If no existing OAuth account and no user found by email (or email not provided),
        # signal that a new user registration (with username input) is required.
        logger.debug(
            f"New user registration required for {provider_name} ID {provider_user_id}."
        )
        return None  # Signal that username is required

    async def register_oauth_user(
        self,
        session: AsyncSession,
        pending_token: str,
        username: str,
    ) -> OAuthAuthenticationResult:
        """
        Registers a new user based on a pending OAuth flow, using the provided username.
        """
        pending_data = self._validate_oauth_pending_registration_token(pending_token)

        # Create the user
        user_create_data = UserCreate(
            username=username,
            email=pending_data.provider_email,
            roles=DEFAULT_USER_ROLE,
            is_guest=False,
        )
        try:
            new_user = await self.user_repository.create_and_commit(
                session, user_create_data.model_dump()
            )
            logger.info(
                f"New user '{username}' (ID: {new_user.id}) created from OAuth flow."
            )
        except DuplicateResource:
            raise BadRequestError(
                f"Username '{username}' is already taken. Please choose another."
            )

        # Link the OAuth account to the new user
        oauth_create_data = OAuthAccountCreate(
            oauth_name=pending_data.provider_name,
            provider_user_id=pending_data.provider_user_id,
            provider_email=pending_data.provider_email,
        )
        await self.oauth_account_repository.create_oauth_account(
            session, oauth_create_data, new_user.id
        )
        logger.debug(
            f"OAuth account for {pending_data.provider_name} linked to new user ID {new_user.id}."
        )

        # Authenticate and return the new user
        return OAuthAuthenticationResult(
            status=OAuthFlowStatus.USER_AUTHENTICATED,
            user=new_user,
            pending_registration_token=None,
        )

    async def authenticate_via_oauth(
        self,
        session: AsyncSession,
        provider_name: str,
        provider_user_id: str,
        provider_email: str | None,
        provider_display_name: str | None = None,
    ) -> OAuthAuthenticationResult:
        logger.debug(
            f"Authenticating via OAuth: Provider='{provider_name}', ProviderUserID='{provider_user_id}', Email='{provider_email}'"
        )
        try:
            user_orm = await self._get_or_create_user_from_oauth(
                session,
                provider_name,
                provider_user_id,
                provider_email,
            )

            if user_orm:
                # Existing user found and linked (or already linked)
                validated_user_orm = await self._validate_user_status_for_login(
                    session, user_orm
                )
                logger.debug(
                    f"OAuth authentication successful for existing user '{validated_user_orm.username}' (ID: {validated_user_orm.id})."
                )
                # Return the full ORM model directly
                return OAuthAuthenticationResult(
                    status=OAuthFlowStatus.USER_AUTHENTICATED,
                    user=validated_user_orm,
                    pending_registration_token=None,
                )
            else:
                # New user, username registration is required
                logger.debug(
                    f"OAuth flow requires username registration for {provider_name} user {provider_user_id}."
                )
                pending_token = self._create_oauth_pending_registration_token(
                    provider_name=provider_name,
                    provider_user_id=provider_user_id,
                    provider_email=provider_email,
                    provider_display_name=provider_display_name,
                )
                return OAuthAuthenticationResult(
                    status=OAuthFlowStatus.USERNAME_REGISTRATION_REQUIRED,
                    user=None,
                    pending_registration_token=pending_token,
                )

        except (
            UserDisabledError,
            UserBannedError,
            InvalidCredentials,
            DuplicateResource,
        ) as e:
            logger.warning(
                f"OAuth authentication failed for {provider_name} user {provider_user_id}: {getattr(e, 'detail', str(e))}"
            )
            raise e
        except ResourceNotFound as e:  # This might occur if _validate_user_status_for_login fails to find a user that _get_or_create thought existed
            logger.error(
                f"OAuth authentication led to unexpected ResourceNotFound: {getattr(e, 'detail', str(e))}"
            )
            raise InvalidCredentials(
                "Failed to link or find your account via OAuth."
            ) from e

    async def login_as_guest(
        self, session: AsyncSession, ip_address: str
    ) -> tuple[User, TokenFullDetail]:
        """
        Finds an existing guest user by IP or creates a new one,
        and returns the user ORM object and full token details.
        """
        try:
            # Attempt to find an existing guest user by IP address
            guest_user = await self.user_repository.get_guest_by_ip(session, ip_address)
            logger.info(
                f"Found existing guest user {guest_user.id} for IP {ip_address}"
            )
        except ResourceNotFound:
            logger.info(
                f"No existing guest user found for IP {ip_address}. Creating a new one."
            )
            # If no existing guest user, create a new one
            guest_username_prefix = "guest"
            guest_username_suffix = str(uuid4())[:8]
            guest_username = f"{guest_username_prefix}{guest_username_suffix}"
            logger.debug(f"Attempting to create guest user: {guest_username}")

            guest_user_data = UserCreate(
                username=guest_username,
                roles=UserRoles.GUEST.value,
                is_guest=True,
                ip_address=ip_address,
            )
            try:
                guest_user = await self.user_repository.create(session, guest_user_data)
                logger.info(
                    f"Guest user '{guest_user.username}' (ID: {guest_user.id}) created successfully for IP {ip_address}."
                )
            except DuplicateResource:
                # Possible as we're not using full uuids
                logger.error(
                    f"Failed to create guest user due to username conflict: {guest_username}"
                )
                raise AppException(
                    "Could not create guest user due to a conflict. Please try again."
                )

        # Validate the user status (is_active, etc.) and update activity timestamp
        validated_guest_user = await self._validate_user_status_for_login(
            session, guest_user
        )
        validated_guest_user.updated_at = datetime.now(timezone.utc)
        session.add(validated_guest_user)
        await session.flush()

        # Generate tokens for the new or existing guest user
        token_details = await self.get_access_token(
            session,
            scopes=[],  # Request no specific scopes, will get all default GUEST scopes
            username=validated_guest_user.username,
            user_object=validated_guest_user,
        )
        return validated_guest_user, token_details

    async def _get_validated_user_for_token_creation(
        self,
        session: AsyncSession,
        username: str,
        password: str | None = None,
        user_object: User | None = None,
    ) -> User:
        """Helper to fetch and validate a user for token creation."""
        if user_object:
            # If a user object is passed, we still run it through validation
            # to handle disabled status, bans etc., as the object might be stale.
            return await self._validate_user_status_for_login(session, user_object)

        if password:
            return await self.authenticate_user(session, username, password)

        try:
            fetched_user = await self.user_repository.get_by_attribute(
                session, username, "username"
            )
            return await self._validate_user_status_for_login(session, fetched_user)
        except ResourceNotFound:
            logger.error(f"Token creation failed: User '{username}' not found.")
            raise InvalidCredentials("User not found for token creation.")

    def _get_granted_scopes(
        self,
        requested_granular_scopes: list[str],
        user_object: User,
    ) -> set[str]:
        """
        Determines the final set of granted scopes for a user based on their roles and requested scopes.
        """
        user_abstract_role_strings = (
            user_object.roles.split() if user_object.roles else []
        )
        user_abstract_roles_enums: set[UserRoles] = set()
        for role_str in user_abstract_role_strings:
            try:
                user_abstract_roles_enums.add(UserRoles(role_str))
            except ValueError:
                logger.warning(
                    f"User {user_object.username} has an invalid role string: '{role_str}'. Ignoring."
                )

        possessed_granular_scopes = get_scopes_for_role_strings(
            user_abstract_role_strings
        )
        requested_scopes_set = set(requested_granular_scopes)
        all_defined_system_scopes = get_all_defined_scopes()
        is_admin_role_present = UserRoles.ADMINISTRATOR in user_abstract_roles_enums

        if is_admin_role_present:
            if requested_scopes_set:
                final_granted_scopes_set = requested_scopes_set.intersection(
                    all_defined_system_scopes
                )
            else:
                final_granted_scopes_set = ROLE_SCOPES_MAPPING.get(
                    UserRoles.ADMINISTRATOR, set()
                ).copy()
        else:
            if requested_scopes_set:
                if not requested_scopes_set.issubset(possessed_granular_scopes):
                    missing_scopes = requested_scopes_set - possessed_granular_scopes
                    logger.warning(
                        f"User '{user_object.username}' requested scopes they do not possess: {missing_scopes}."
                    )
                    raise PermissionDenied(
                        f"Requested scopes {missing_scopes} are not permitted for this user."
                    )
                final_granted_scopes_set = requested_scopes_set
            else:
                final_granted_scopes_set = possessed_granular_scopes.copy()

        return final_granted_scopes_set.intersection(all_defined_system_scopes)

    async def create_access_token(
        self,
        requested_granular_scopes: list[str],
        user_object: User,
    ) -> tuple[str, datetime]:
        """
        Creates a JWT access token for a given, validated user object.
        This method NO LONGER fetches or validates the user.
        Returns the token string and its expiration datetime.
        """
        final_granted_scopes_set = self._get_granted_scopes(
            requested_granular_scopes, user_object
        )
        user_abstract_role_strings = (
            user_object.roles.split() if user_object.roles else []
        )

        expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
        expire = datetime.now(timezone.utc) + expires_delta

        token_payload = TokenData(
            sub=user_object.username,
            uid=user_object.id,
            roles=user_abstract_role_strings,
            scopes=sorted(list(final_granted_scopes_set)),
            is_guest=user_object.is_guest,
        )

        to_encode = token_payload.model_dump(mode="json")
        to_encode["exp"] = int(expire.timestamp())

        encoded_jwt = jwt.encode(
            to_encode, settings.secret_key, algorithm=settings.algorithm
        )
        return encoded_jwt, expire

    async def get_access_token(
        self,
        session: AsyncSession,
        scopes: list[str],
        username: str,
        password: str | None = None,
        user_object: User | None = None,
    ) -> TokenFullDetail:
        """
        Main method to generate a new token pair (access and refresh).
        It validates the user and then creates both tokens.
        """
        validated_user = await self._get_validated_user_for_token_creation(
            session, username, password, user_object
        )

        access_token_str, expires_at_dt = await self.create_access_token(
            requested_granular_scopes=scopes,
            user_object=validated_user,
        )

        refresh_token_str = await self._create_refresh_token(session, validated_user)

        return TokenFullDetail(
            access_token=access_token_str,
            token_type="bearer",
            refresh_token=refresh_token_str,
            expires_at=expires_at_dt,
        )

    async def refresh_access_token(
        self, session: AsyncSession, refresh_token_str: str
    ) -> TokenFullDetail:
        """
        Takes a refresh token, validates it, revokes it, and issues a new
        access/refresh token pair.
        """
        logger.debug("Attempting to refresh access token.")

        # 1. Validate the old refresh token. This also validates the user.
        old_db_token, user = await self._validate_refresh_token(
            session, refresh_token_str
        )

        # 2. Revoke the old refresh token (Token Rotation)
        await self.refresh_token_repository.revoke_token(session, old_db_token.jti)
        logger.debug(
            f"Revoked refresh token jti={old_db_token.jti} for user {user.username}"
        )

        # 3. Issue a new access token and a new refresh token
        new_token_details = await self.get_access_token(
            session=session,
            scopes=[],  # Default scopes for the user's roles
            username=user.username,
            user_object=user,
        )

        logger.debug(f"Successfully refreshed token for user {user.username}.")
        return new_token_details

    async def revoke_refresh_token(self, session: AsyncSession, refresh_token_str: str):
        """
        Validates and revokes a refresh token, effectively logging the user out.
        """
        logger.debug("Attempting to revoke refresh token for logout.")
        try:
            # _validate_refresh_token also checks for prior revocation, expiry, and user status.
            # We don't need the user object here, but validation is important.
            db_token, _ = await self._validate_refresh_token(session, refresh_token_str)

            # Revoke the token
            await self.refresh_token_repository.revoke_token(session, db_token.jti)
            logger.debug(
                f"Successfully revoked refresh token jti={db_token.jti} for logout."
            )
        except InvalidCredentials as e:
            # If the token is already invalid/revoked/expired, we can treat logout as successful.
            logger.warning(
                f"Logout attempted with an invalid refresh token: {e.detail}"
            )
            # Do not re-raise, as the goal is to ensure the user is logged out.
        except Exception as e:
            logger.exception(
                "Unexpected error during refresh token revocation for logout."
            )
            # For logout, fail silently on the server-side
            # and let the client clear its state.
