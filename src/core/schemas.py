# src.core.schemas
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UuidMixin:
    """A mixin to add a UUID primary key field to a Pydantic model."""

    id: UUID | None = None


class Base(BaseModel):
    """Base Pydantic model with ORM mode enabled.

    Attributes:
        model_config: Pydantic configuration to allow creating schemas
                      from ORM model instances (from_attributes=True).
    """

    model_config = ConfigDict(from_attributes=True)
