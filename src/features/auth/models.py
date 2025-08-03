# src.features.auth.models
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.models import Base, UuidMixin

if TYPE_CHECKING:
    from src.features.users.models import User  # Import User only for type checking


class OAuthAccount(Base, UuidMixin):
    __tablename__ = "oauth_accounts"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    oauth_name: Mapped[str] = mapped_column(
        String(50), index=True
    )  # like  "google", "apple"
    provider_user_id: Mapped[str] = mapped_column(
        String(255), index=True
    )  # ID from the OAuth provider
    provider_email: Mapped[str | None] = mapped_column(
        String(255), index=True, nullable=True
    )  # Email from OAuth provider

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationship to User
    user: Mapped["User"] = relationship(
        back_populates="oauth_accounts", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint(
            "oauth_name", "provider_user_id", name="uq_oauth_provider_user"
        ),
    )

    def __repr__(self):
        return f"<OAuthAccount(id={self.id}, provider='{self.oauth_name}', provider_user_id='{self.provider_user_id}', user_id='{self.user_id}')>"


class RefreshToken(Base, UuidMixin):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    jti: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationship to User
    user: Mapped["User"] = relationship(back_populates="refresh_tokens")

    def __repr__(self):
        return f"<RefreshToken(id={self.id}, jti='{self.jti}', user_id='{self.user_id}', revoked_at='{self.revoked_at}')>"
