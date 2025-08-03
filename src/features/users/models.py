# src.features.users.models
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.models import Base, UuidMixin

if TYPE_CHECKING:
    from src.features.auth.models import (
        OAuthAccount,
        RefreshToken,
    )


class User(Base, UuidMixin):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(50), index=True, unique=True)
    email: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    roles: Mapped[str] = mapped_column(
        String(255), default=""
    )  # whitespace separated user roles ie: "PLAYER MODERATOR"
    is_guest: Mapped[bool] = mapped_column(default=False, index=True)
    ip_address: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )

    is_active: Mapped[bool] = mapped_column(default=True, index=True)
    disabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    bans_issued: Mapped[list["Ban"]] = relationship(
        "Ban", back_populates="banned_by_user", foreign_keys="Ban.banned_by_id"
    )
    bans_received: Mapped[list["Ban"]] = relationship(
        "Ban",
        back_populates="user",
        foreign_keys="Ban.user_id",
        cascade="all, delete-orphan",
    )
    oauth_accounts: Mapped[list["OAuthAccount"]] = relationship(
        "OAuthAccount",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",  # Todo: consider performance of "joined", "subquery" or "selectin"
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Ban(Base, UuidMixin):
    __tablename__ = "bans"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    reason: Mapped[str | None] = mapped_column(nullable=True)
    banned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # Null for permanent ban

    banned_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )  # Admin who issued the ban

    is_currently_active: Mapped[bool] = mapped_column(
        default=True, index=True
    )  # To quickly query/filter active bans
    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # When the ban was manually made inactive
    deactivated_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )  # Admin who deactivated the ban

    # Relationships
    user: Mapped["User"] = relationship(
        "User", back_populates="bans_received", foreign_keys=[user_id]
    )
    banned_by_user: Mapped["User | None"] = relationship(
        "User", back_populates="bans_issued", foreign_keys=[banned_by_id]
    )
