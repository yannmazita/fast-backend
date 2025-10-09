# src.common.utils.settings
import structlog
from typing import Annotated, Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BeforeValidator, EmailStr, HttpUrl, PostgresDsn, model_validator

logger = structlog.get_logger(__name__)


def strip_whitespace(v: str | None) -> str | None:
    if isinstance(v, str):
        return v.strip()
    return v


StrippedStr = Annotated[str, BeforeValidator(strip_whitespace)]
OptionalStrippedStr = Annotated[str | None, BeforeValidator(strip_whitespace)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    # Environment
    environment: Literal["DEV", "PROD"] = "DEV"
    uvicorn_log_level: Literal["info", "debug", "warning"] = "debug"
    fastapi_log_level: Literal["info", "debug", "warning"] = "info"

    # Frontend
    dev_frontend_base_url: HttpUrl = HttpUrl("http://localhost:5173")
    prod_frontend_base_url: HttpUrl | None = None
    frontend_oauth_success_path: str = "/auth/callback"
    frontend_oauth_error_path: str = "/auth/error"
    frontend_oauth_complete_registration_path: str = "/auth/complete-registration"

    # GCS
    dev_uploads_gcs_bucket_name: str = "fastbackend-dev-uploads"
    prod_uploads_gcs_bucket_name: str | None = None
    uploads_custom_domain: HttpUrl | None = None
    frontend_gcs_base_url: HttpUrl = HttpUrl("https://storage.googleapis.com")
    gcs_signer_service_account_email: EmailStr | None = None

    # API
    prod_api_base_url: HttpUrl | None = None  # ex: "https://api.supercoolapp.com"
    origins: list[
        str
    ]  # ex: ORIGINS='["http://localhost:5173", "https://supercoolapp.com"]'
    uvicorn_host: str = "0.0.0.0"
    port: int = 8080

    # Administration
    admin_username: StrippedStr
    admin_email: EmailStr
    admin_password: StrippedStr

    # Secrets
    secret_key: StrippedStr
    algorithm: StrippedStr

    # Users
    guest_account_cleanup_days: int = 15
    disabled_account_cleanup_days: int = 30
    inactive_registered_account_cleanup_days: int = 365

    # JWT
    access_token_expire_minutes: int = 60
    refresh_token_expire_minutes: int = 43200  # 30 days

    # Refresh Token Cookie
    refresh_token_cookie_name: str = "fastbackend_refresh_token"
    refresh_token_cookie_path: str = "/auth"
    refresh_token_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    refresh_token_cookie_secure: bool = (
        True  # Should be False in .env for local HTTP dev
    )
    refresh_token_cookie_httponly: bool = True

    # OAuth State Cookie
    oauth_state_cookie_name: str = "fastbackend_oauth_state"
    oauth_state_expire_minutes: int = 60
    oauth_pending_registration_token_expire_minutes: int = 15

    # Google OAuth
    google_client_id: OptionalStrippedStr = None
    google_client_secret: OptionalStrippedStr = None
    google_redirect_uri_path: str = "/auth/oauth/google/callback"  # Path part

    # Apple OAuth
    apple_client_id: OptionalStrippedStr = None  # Service ID
    apple_team_id: OptionalStrippedStr = None
    apple_key_id: OptionalStrippedStr = None
    apple_private_key: str | None = None  # Multi-line string
    apple_redirect_uri_path: str = "/auth/oauth/apple/callback"  # Path part

    # Postgres
    postgres_user: StrippedStr
    postgres_password: StrippedStr
    postgres_db: StrippedStr
    postgres_host: StrippedStr  # For DEV: localhost, For PROD: db.trackguessr.com
    postgres_port: int
    postgres_echo: bool = False

    @property
    def frontend_base_url(self) -> HttpUrl:
        if self.environment == "PROD":
            if not self.prod_frontend_base_url:
                raise ValueError(
                    "PROD_FRONTEND_BASE_URL must be set in PROD environment."
                )
            return self.prod_frontend_base_url
        return self.dev_frontend_base_url

    @property
    def api_base_url(self) -> HttpUrl:
        if self.environment == "PROD":
            if not self.prod_api_base_url:
                raise ValueError("PROD_API_BASE_URL must be set in PROD environment.")
            return self.prod_api_base_url
        dev_api_host = (
            "localhost" if self.uvicorn_host == "0.0.0.0" else self.uvicorn_host
        )
        return HttpUrl(f"http://{dev_api_host}:{self.port}")

    @property
    def frontend_success_redirect_uri(self) -> str:
        return (
            str(self.frontend_base_url).rstrip("/") + self.frontend_oauth_success_path
        )

    @property
    def frontend_error_redirect_uri(self) -> str:
        return str(self.frontend_base_url).rstrip("/") + self.frontend_oauth_error_path

    @property
    def frontend_oauth_complete_registration_redirect_uri(self) -> str:
        return (
            str(self.frontend_base_url).rstrip("/")
            + self.frontend_oauth_complete_registration_path
        )

    @property
    def google_redirect_uri(self) -> str | None:
        if not self.google_client_id:
            return None
        return str(self.api_base_url).rstrip("/") + self.google_redirect_uri_path

    @property
    def apple_redirect_uri(self) -> str | None:
        if not self.apple_client_id:
            return None
        return str(self.api_base_url).rstrip("/") + self.apple_redirect_uri_path

    @property
    def uploads_gcs_bucket_name(self) -> str:
        if self.environment == "PROD":
            if not self.prod_uploads_gcs_bucket_name:
                raise ValueError(
                    "PROD_UPLOADS_GCS_BUCKET_NAME must be set in PROD environment."
                )
            return self.prod_uploads_gcs_bucket_name
        return self.dev_uploads_gcs_bucket_name

    @property
    def gcs_asset_url(self) -> str:
        # In production, use the custom CDN domain for optimal performance and cost.
        # To do: cloudflare R2 and custom domain
        if self.environment == "PROD" and self.uploads_custom_domain:
            return str(self.uploads_custom_domain).rstrip("/")

        return f"{str(self.frontend_gcs_base_url).rstrip('/')}/{self.uploads_gcs_bucket_name}"

    @property
    def async_postgres_base_url(self) -> PostgresDsn:
        return PostgresDsn(
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ssl_append = ""
    # if self.environment == "PROD":
    #    ssl_append = "?ssl=require"
    # else:
    #    ssl_append = ""
    # return PostgresDsn(
    #    f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}{ssl_append}"
    # )  # enforcing TLS (might not be necessary)

    @model_validator(mode="after")
    def _check_configurations(self) -> "Settings":
        if self.environment == "PROD":
            if not self.prod_frontend_base_url:
                raise ValueError(
                    "PROD_FRONTEND_BASE_URL is required in PROD environment."
                )
            if not self.prod_api_base_url:
                raise ValueError("PROD_API_BASE_URL is required in PROD environment.")
            # Actually not required, we're directly using the GCS link, we'll a get custom domain when migrating to R2
            # if not self.uploads_custom_domain:
            #    raise ValueError(
            #        "UPLOADS_CUSTOM_DOMAIN is required in PROD environment."
            #    )
            if (
                "localhost" in str(self.postgres_host).lower()
                and self.environment == "PROD"
            ):
                logger.warning(
                    f"Postgres host '{self.postgres_host}' in PROD environment might be incorrect. Expected a remote host."
                )
        if self.google_client_id:
            if (
                not self.google_redirect_uri_path
                or not self.google_redirect_uri_path.startswith("/")
            ):
                raise ValueError(
                    "If google_client_id is set, google_redirect_uri_path must be a non-empty valid path string (like  '/auth/oauth/google/callback')."
                )
            if not self.google_client_secret:
                raise ValueError(
                    "google_client_secret must be set if google_client_id is provided."
                )

        if self.apple_client_id:
            if (
                not self.apple_redirect_uri_path
                or not self.apple_redirect_uri_path.startswith("/")
            ):
                raise ValueError(
                    "If apple_client_id is set, apple_redirect_uri_path must be a non-empty valid path string (like  '/auth/oauth/apple/callback')."
                )
            if not (
                self.apple_team_id and self.apple_key_id and self.apple_private_key
            ):
                raise ValueError(
                    "apple_team_id, apple_key_id, and apple_private_key must be set if apple_client_id is provided."
                )

        if (
            not self.frontend_oauth_success_path
            or not self.frontend_oauth_success_path.startswith("/")
        ):
            raise ValueError(
                "frontend_oauth_success_path must be a non-empty valid path string."
            )
        if (
            not self.frontend_oauth_error_path
            or not self.frontend_oauth_error_path.startswith("/")
        ):
            raise ValueError(
                "frontend_oauth_error_path must be a non-empty valid path string."
            )
        if (
            not self.frontend_oauth_complete_registration_path
            or not self.frontend_oauth_complete_registration_path.startswith("/")
        ):
            raise ValueError(
                "frontend_oauth_complete_registration_path must be a non-empty valid path string."
            )

        if not self.postgres_db or len(self.postgres_db.strip()) == 0:
            raise ValueError(
                "POSTGRES_DB environment variable must be set and cannot be empty."
            )

        return self

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        logger.debug(f"Settings loaded for environment: {self.environment}")
        if self.environment == "PROD":
            logger.debug(f"Production Frontend Base URL: {self.prod_frontend_base_url}")
            logger.debug(f"Production API Base URL: {self.prod_api_base_url}")
        else:
            logger.debug(f"Development Frontend Base URL: {self.frontend_base_url}")
            logger.debug(f"Development API Base URL: {self.api_base_url}")

        if self.google_client_id:
            logger.debug(
                f"Google OAuth configured, redirect URI: {self.google_redirect_uri}"
            )
        if self.apple_client_id:
            logger.debug(
                f"Apple OAuth configured, redirect URI: {self.apple_redirect_uri}"
            )
        logger.debug(
            f"Postgres connection configured for: {self.async_postgres_base_url}"
        )
        logger.debug(f"GCS Asset URL configured for: {self.gcs_asset_url}")
        logger.debug(
            f"OAuth complete registration redirect URI: {self.frontend_oauth_complete_registration_redirect_uri}"
        )


settings = Settings()
