# src/manage.py
import sys
import os
import typer
import asyncio
import structlog
from sqlalchemy import text

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.common.database import sessionmanager
from src.common.utils.settings import settings
from src.features.users.services.cleanup import UserCleanupService

logger = structlog.get_logger(__name__)

app = typer.Typer()


async def cleanup_main():
    sessionmanager.__init__(
        settings.async_postgres_base_url.unicode_string(),
        {"echo": settings.postgres_echo},
    )
    async with sessionmanager.session() as session:
        cleanup_service = UserCleanupService(session)

        # Cleanup inactive guest accounts
        inactive_guests = await cleanup_service.get_inactive_guest_accounts()
        if inactive_guests:
            logger.info(f"Found {len(inactive_guests)} inactive guest accounts to delete.")
            for user in inactive_guests:
                await cleanup_service.delete_user(user)
        else:
            logger.info("No inactive guest accounts to delete.")

        # Cleanup disabled accounts
        disabled_accounts = await cleanup_service.get_disabled_accounts_for_cleanup()
        if disabled_accounts:
            logger.info(
                f"Found {len(disabled_accounts)} disabled accounts to delete."
            )
            for user in disabled_accounts:
                await cleanup_service.delete_user(user)
        else:
            logger.info("No disabled accounts to delete.")

        # Cleanup inactive registered accounts
        inactive_registered = (
            await cleanup_service.get_inactive_registered_accounts()
        )
        if inactive_registered:
            logger.info(
                f"Found {len(inactive_registered)} inactive registered accounts to delete."
            )
            for user in inactive_registered:
                await cleanup_service.delete_user(user)
        else:
            logger.info("No inactive registered accounts to delete.")


@app.command()
def cleanup_users():
    """
    Finds and deletes inactive guest accounts and long-disabled user accounts.
    """
    logger.info("Starting user cleanup process...")
    asyncio.run(cleanup_main())
    logger.info("User cleanup process finished.")


async def clear_sessions_main():
    sessionmanager.__init__(
        settings.async_postgres_base_url.unicode_string(),
        {"echo": settings.postgres_echo},
    )
    async with sessionmanager.session() as session:
        logger.info("Deleting all records from game_sessions table...")
        await session.execute(text("DELETE FROM game_sessions"))
        await session.commit()
        logger.info("All game sessions have been cleared.")


@app.command()
def clear_all_game_sessions(
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt.",
    )
):
    """
    Deletes every single game session from the database.
    """
    if yes or typer.confirm(
        "Are you sure you want to delete all game sessions? This action is irreversible."
    ):
        logger.info("Starting process to clear all game sessions...")
        asyncio.run(clear_sessions_main())
        logger.info("Finished clearing all game sessions.")
    else:
        logger.info("Operation cancelled.")


if __name__ == "__main__":
    app()
