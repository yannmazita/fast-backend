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
    """Generic repository for performing database operations on a model.

    This class provides a set of common CRUD (Create, Read, Update, Delete)
    operations for a given SQLAlchemy model.

    Attributes:
        model: The SQLAlchemy model class this repository operates on.
    """

    def __init__(self, model: type[Model]) -> None:
        """Initializes the DatabaseRepository.

        Args:
            model: The SQLAlchemy model class.
        """
        self.model: type[Model] = model

    async def create(self, session: AsyncSession, data: dict[str, Any]) -> Model:
        """Creates a new model instance in the database.

        This method adds the instance to the session and flushes, but does
        not commit the transaction.

        Args:
            session: The database session.
            data: A dictionary of data for the new instance.

        Returns:
            The newly created model instance.

        Raises:
            DuplicateResource: If creating the resource violates a unique
                               constraint.
            SQLAlchemyError: For other database-related errors.
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
        """Creates a new model instance and commits the transaction.

        Args:
            session: The database session.
            data: A dictionary of data for the new instance.

        Returns:
            The newly created and refreshed model instance.

        Raises:
            DuplicateResource: If creating the resource violates a unique
                               constraint.
            SQLAlchemyError: For other database-related errors.
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
        """Retrieves a model instance by a specific attribute.

        Args:
            session: The database session.
            value: The value of the attribute to filter by.
            column: The name of the model's column attribute to filter on.
            with_for_update: If True, locks the selected row for update.

        Returns:
            The found model instance.

        Raises:
            ResourceNotFound: If no instance is found with the given attribute.
            SQLAlchemyError: For other database-related errors.
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
        """Updates a model instance identified by a specific attribute.

        Args:
            session: The database session.
            data: A dictionary of attributes to update.
            value: The value of the attribute to identify the instance.
            column: The name of the column attribute to identify the instance.
            none_replace: If True, attributes with None values in `data` will
                          be set to None in the database.

        Returns:
            The updated model instance.

        Raises:
            ResourceNotFound: If the instance to update is not found.
            DuplicateResource: If the update violates a unique constraint.
            SQLAlchemyError: For other database-related errors.
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
        """Deletes a model instance identified by a specific attribute.

        Args:
            session: The database session.
            value: The value of the attribute to identify the instance.
            column: The name of the column attribute to identify the instance.

        Returns:
            The model instance data before it was deleted.

        Raises:
            ResourceNotFound: If the instance to delete is not found.
            SQLAlchemyError: For database-related errors, such as foreign
                             key violations.
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
        """Retrieves all instances of the model with pagination.

        Args:
            session: The database session.
            offset: The number of records to skip.
            limit: The maximum number of records to return.

        Returns:
            A tuple containing a list of model instances and the total
            count of all instances in the table.

        Raises:
            SQLAlchemyError: For database-related errors.
        """
        total_count_query = select(func.count()).select_from(self.model)
        total_count_response = await session.execute(total_count_query)
        total_count: int = total_count_response.scalar_one()

        query = select(self.model).offset(offset).limit(limit)
        response = await session.execute(query)
        instances = response.scalars().all()
        return instances, total_count
