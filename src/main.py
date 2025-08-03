# src/main.py
import structlog
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from src.common.database import sessionmanager
from src.common.logging import configure_logging
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
from src.features.auth import router as auth_routes
from src.features.users import router as user_routes
from src.features.users.utils.management import create_superuser

logger = structlog.get_logger(__name__)


# --- Exception Handlers ---
async def app_exception_handler(request: Request, exc: AppException):
    """
    Handles application-specific exceptions, returning a standardized JSON response.
    """
    error_code = None
    if isinstance(exc, InvalidCredentials):
        error_code = "INVALID_CREDENTIALS"
    elif isinstance(exc, PermissionDenied):
        error_code = "PERMISSION_DENIED"
    elif isinstance(exc, UserBannedError):
        error_code = "USER_BANNED"
    elif isinstance(exc, UserDisabledError):
        error_code = "USER_DISABLED"
    elif isinstance(exc, ResourceNotFound):
        error_code = "RESOURCE_NOT_FOUND"
    elif isinstance(exc, DuplicateResource):
        error_code = "DUPLICATE_RESOURCE"
    elif isinstance(exc, BadRequestError):
        error_code = "BAD_REQUEST"

    content = {"detail": exc.detail}
    if error_code:
        content["error_code"] = error_code

    return JSONResponse(
        status_code=exc.status_code,
        content=content,
    )


async def http_exception_handler(request: Request, exc: Exception):
    """
    Centralized exception handler for the application.
    It logs the exception and returns a standardized JSON response.
    """
    logger.error(
        "An unhandled exception occurred",
        exc_info=True,
        method=request.method,
        url=str(request.url),
        headers=dict(request.headers),
    )

    # Default status code and detail
    status_code = 500
    detail = "An unexpected internal server error occurred."
    error_code = None

    if isinstance(exc, SQLAlchemyError):
        detail = "An internal database error occurred."

    content = {"detail": detail}
    if error_code:
        content["error_code"] = error_code

    return JSONResponse(
        status_code=status_code,
        content=content,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Configure logging
    configure_logging(settings.fastapi_log_level.upper())

    # Initialize the database session manager
    sessionmanager.__init__(
        settings.async_postgres_base_url.unicode_string(),
        {"echo": settings.postgres_echo},
    )
    logger.info("Application startup...")
    try:
        logger.info("Attempting to create/verify superuser...")
        await create_superuser()
        logger.info("Superuser creation/verification step completed.")

        if settings.environment == "DEV":
            pass
        else:
            logger.info("Skipping DEV environment init (PROD environment).")
    except Exception as e:
        logger.exception("Critical error during application startup.", exc_info=True)
    yield
    logger.info("Application shutdown...")
    if sessionmanager._engine is not None:
        logger.info("Closing database connection pool.")
        await sessionmanager.close()
        logger.info("Database connection pool closed.")
    logger.info("Application shutdown complete.")


api = FastAPI(
    title="fast-backend",
    version="0.1.0",
    lifespan=lifespan,
)

api.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Exception Handlers
api.add_exception_handler(Exception, http_exception_handler)
api.add_exception_handler(AppException, app_exception_handler)


api.include_router(auth_routes.router)
api.include_router(user_routes.router)


def start_server():
    uvicorn.run(
        "src.main:api",
        host=settings.uvicorn_host,
        port=int(settings.port),
        log_config=None,
        reload=settings.environment == "DEV",
    )


if __name__ == "__main__":
    start_server()
