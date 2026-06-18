# src/core/models.py
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class UuidMixin:
    """A mixin to add a UUID primary key column to a SQLAlchemy model."""

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all SQLAlchemy ORM models.

    Includes support for asynchronous attribute loading.
    """

    pass
