# src/common/repository
import structlog
from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import (
    func,
    select,
)
from sqlalchemy.exc import (
    IntegrityError,
    SQLAlchemyError,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import (
    DuplicateResource,
    ResourceNotFound,
)
from src.core.models import Base
from src.core.schemas import Base as BaseSchema

logger = structlog.get_logger(__name__)

Model = TypeVar("Model", bound=Base)
Schema = TypeVar("Schema", bound=BaseSchema)  # for future potential generic methods


class DatabaseRepository(Generic[Model, Schema]):
    """
    Repository for performing database queries.

    Attributes:
        model: The model to be used for queries.
    """

    def __init__(self, model: type[Model]) -> None:
        self.model: type[Model] = model

    async def create(self, session: AsyncSession, data: dict[str, Any]) -> Model:
        """
        Create a new instance of the model in the database from a dictionary.
        This method does not commit the transaction, allowing it to be used
        in larger transactions in the service layer.

        Args:
            session: The database session to be used for queries.
            data: A dictionary containing data for creation. Keys should
                  correspond to model attribute names.
        Returns:
            The created instance.
        Raises:
            DuplicateResource: If a unique constraint is violated.
            SQLAlchemyError: For other database errors.
            AppException: For unexpected errors.
        """
        try:
            # Instantiate the model directly from the dictionary
            instance = self.model(**data)
            session.add(instance)
            await session.flush()
            return instance
        except IntegrityError as e:
            await session.rollback()
            # Attempt to get the PostgreSQL error code
            pgcode = getattr(
                getattr(e.orig, "diag", None), "sqlstate", None
            ) or getattr(e.orig, "pgcode", None)
            # Check specifically for unique violation code '23505'
            if pgcode == "23505":
                # Log the detailed error for internal debugging
                logger.warning(
                    f"Unique constraint violation during create: {e}", exc_info=False
                )
                # Raise DuplicateResource with a generic message for the client
                raise DuplicateResource(
                    detail="Resource creation failed due to a conflict with existing data."
                ) from e
            else:
                logger.exception("Integrity error occurred.", stack_info=True)
                raise SQLAlchemyError("Database integrity error") from e
        except SQLAlchemyError as e:
            await session.rollback()
            logger.exception(
                "SQLAlchemy error occurred during create.", stack_info=True
            )
            raise e

    async def create_and_commit(
        self, session: AsyncSession, data: dict[str, Any]
    ) -> Model:
        """
        Create a new instance of the model in the database from a dictionary
        and commits the transaction.

        Args:
            session: The database session to be used for queries.
            data: A dictionary containing data for creation. Keys should
                  correspond to model attribute names.
        Returns:
            The created instance.
        Raises:
            DuplicateResource: If a unique constraint is violated.
            SQLAlchemyError: For other database errors.
            AppException: For unexpected errors.
        """
        instance = await self.create(session, data)
        await session.commit()
        await session.refresh(instance)
        return instance

    async def get_by_attribute(
        self,
        session: AsyncSession,
        value: UUID | str,
        column: str = "id",
        with_for_update: bool = False,
    ) -> Model:
        """
        Get an instance of the model from the database.

        Args:
            session: The database session to be used for queries.
            value: The value of the attribute to be used for filtering.
            column: The column to be used for filtering.
            with_for_update: Lock the row for update.
        Returns:
            The retrieved instance.
        Raises:
            ResourceNotFound: If no instance is found.
            AppException: For multiple results or unexpected errors.
            SQLAlchemyError: For database errors.
        """
        query = select(self.model).where(getattr(self.model, column) == value)

        if with_for_update:
            query = query.with_for_update()

        response = await session.execute(query)
        instance = response.scalar_one_or_none()
        if not instance:
            raise ResourceNotFound(f"Resource with {column} = {value} not found.")
        return instance

    async def update_by_attribute(
        self,
        session: AsyncSession,
        data: dict[str, Any],
        value: UUID | str,
        column: str = "id",
        none_replace: bool = False,
    ) -> Model:
        """
        Update an instance of the model in the database using a dictionary.

        Args:
            session: The database session to be used for queries.
            data: A dictionary containing the attributes to update.
                  Keys should correspond to model attribute names.
            value: The value of the attribute to be used for filtering.
            column: The column to be used for filtering.
            none_replace: Whether to replace existing values with None if
                          None is provided in the data dictionary.
        Returns:
            The updated instance.
        Raises:
            ResourceNotFound: If the instance to update is not found.
            DuplicateResource: If the update violates a unique constraint.
            SQLAlchemyError: For other database errors.
            AppException: For unexpected errors.
        """
        # get_by_attribute will raise ResourceNotFound if not found
        instance = await self.get_by_attribute(
            session, value, column, with_for_update=True
        )
        try:
            # Iterate directly over the dictionary items
            for key, val in data.items():
                # Skip None values if none_replace is False
                if val is None and not none_replace:
                    continue
                # Basic check: only update attributes that exist on the model
                if hasattr(instance, key):
                    setattr(instance, key, val)
                else:
                    logger.warning(
                        f"Attempted to update non-existent attribute '{key}' "
                        f"on model {self.model.__name__} for {column}={value}. Skipping."
                    )

            session.add(instance)
            await session.flush()  # Check for errors before commit
            await session.commit()
            await session.refresh(instance)
            return instance
        except IntegrityError as e:
            await session.rollback()
            # Attempt to get the PostgreSQL error code
            pgcode = getattr(
                getattr(e.orig, "diag", None), "sqlstate", None
            ) or getattr(e.orig, "pgcode", None)
            # Check specifically for unique violation code '23505'
            if pgcode == "23505":
                # Log the detailed error for internal debugging
                logger.warning(
                    f"Unique constraint violation during update: {e}", exc_info=False
                )
                raise DuplicateResource(
                    detail="Resource update failed due to a conflict with existing data."
                ) from e
            else:
                # Handle other integrity errors (like  foreign key, check constraint)
                logger.exception(
                    f"Integrity error occurred during update (pgcode: {pgcode}): {e}",
                    stack_info=True,
                )
                raise SQLAlchemyError(
                    f"Database integrity error during resource update: {e}"
                ) from e
        except SQLAlchemyError as e:
            await session.rollback()
            logger.exception(
                "SQLAlchemy error occurred during update.", stack_info=True
            )
            raise SQLAlchemyError(f"SQLAlchemy error occured during update: {e}") from e

    async def delete(
        self, session: AsyncSession, value: UUID | str, column: str = "id"
    ) -> Model:
        """
        Delete an instance of the model from the database.

        Args:
            session: The database session to be used for queries.
            value: The value of the attribute to be used for filtering.
            column: The column to be used for filtering.
        Returns:
            The deleted instance (data before deletion).
        Raises:
            ResourceNotFound: If the instance to delete is not found.
            SQLAlchemyError: For database errors (like  foreign key constraint).
            AppException: For unexpected errors.
        """
        instance = await self.get_by_attribute(session, value, column)
        try:
            await session.delete(instance)
            await session.flush()
            await session.commit()
            return instance
        except IntegrityError as e:
            # Handle integrity errors during delete (like  foreign key constraints)
            await session.rollback()
            logger.exception("Integrity error occurred during delete.", stack_info=True)
            raise SQLAlchemyError(
                f"Cannot delete resource because it is referenced by other data :{e}"
            ) from e
        except SQLAlchemyError as e:
            await session.rollback()
            logger.exception(
                "SQLAlchemy error occurred during delete.", stack_info=True
            )
            raise SQLAlchemyError("SQLAlchemy error occured during delete.") from e

    async def get_all(self, session: AsyncSession, offset: int = 0, limit: int = 100):
        """
        Get all instances of the model from the database with pagination.
        Args:
            session: The database session to be used for queries.
            offset: The number of instances to skip.
            limit: The maximum number of instances to return.
        Returns:
            A tuple containing the list of instances and the total count.
        Raises:
            SQLAlchemyError: For database errors.
            AppException: For unexpected errors.
        """
        total_count_query = select(func.count()).select_from(self.model)
        total_count_response = await session.execute(total_count_query)
        total_count: int = total_count_response.scalar_one()

        query = select(self.model).offset(offset).limit(limit)
        response = await session.execute(query)
        instances = response.scalars().all()
        return instances, total_count
