# src.core.schemas
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UuidMixin:
    id: UUID | None = None


class Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)
