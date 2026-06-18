# src.common.database
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.common.utils.settings import settings


class DatabaseSessionManager:
    """Manages the database engine and session creation.

    This class encapsulates the SQLAlchemy async engine and sessionmaker,
    providing context managers for safe database connections and sessions.

    Attributes:
        _engine: The SQLAlchemy async engine instance.
        _sessionmaker: The SQLAlchemy async sessionmaker instance.
    """

    def __init__(self, host: str, engine_kwargs: dict[str, Any] = {}):
        """Initializes the DatabaseSessionManager.

        Args:
            host: The database connection URL.
            engine_kwargs: A dictionary of keyword arguments to pass to
                           create_async_engine.
        """
        self._engine = create_async_engine(host, **engine_kwargs)
        self._sessionmaker = async_sessionmaker(
            autocommit=False, bind=self._engine, expire_on_commit=False
        )

    async def close(self):
        """Closes the database engine and disposes of the connection pool."""
        if self._engine is None:
            # This can happen if close is called on an uninitialized manager.
            # In a test environment, this is safe to ignore.
            return
        await self._engine.dispose()

        self._engine = None
        self._sessionmaker = None

    @asynccontextmanager
    async def connect(self) -> AsyncGenerator[AsyncConnection]:
        """Provides a database connection from the connection pool.

        This is a context manager that yields a connection and ensures it is
        properly handled.

        Yields:
            An async database connection.

        Raises:
            Exception: If the session manager is not initialized.
        """
        if self._engine is None:
            raise Exception("DatabaseSessionManager is not initialized")

        async with self._engine.begin() as connection:
            try:
                yield connection
            except Exception:
                await connection.rollback()
                raise

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession]:
        """Provides a database session.

        This is a context manager that yields a session, handles rollback
        on exceptions, and ensures the session is closed.

        Yields:
            An async database session.

        Raises:
            Exception: If the session manager is not initialized.
        """
        if self._sessionmaker is None:
            raise Exception("DatabaseSessionManager is not initialized")

        session = self._sessionmaker()
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


sessionmanager = DatabaseSessionManager(
    settings.async_postgres_base_url.unicode_string(), {"echo": settings.postgres_echo}
)


async def get_session() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency to get a database session.

    Yields:
        An async database session managed by the sessionmanager.
    """
    async with sessionmanager.session() as session:
        yield session
