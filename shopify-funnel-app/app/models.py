from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, DeclarativeBase, mapped_column


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ShopInstallation(Base):
    __tablename__ = "shop_installations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shop_domain: Mapped[str] = mapped_column(String(length=255), unique=True, nullable=False, index=True)
    client_id: Mapped[str | None] = mapped_column(String(length=64), nullable=True, index=True)
    admin_access_token: Mapped[str] = mapped_column(Text, nullable=False)
    storefront_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    scopes: Mapped[str] = mapped_column(Text, nullable=False)
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    uninstalled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OAuthState(Base):
    __tablename__ = "oauth_states"

    state: Mapped[str] = mapped_column(String(length=128), primary_key=True)
    shop_domain: Mapped[str] = mapped_column(String(length=255), nullable=False)
    client_id: Mapped[str | None] = mapped_column(String(length=64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ProcessedWebhookEvent(Base):
    __tablename__ = "processed_webhook_events"
    __table_args__ = (
        UniqueConstraint("shop_domain", "topic", "event_id", name="uq_processed_webhook_event"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shop_domain: Mapped[str] = mapped_column(String(length=255), nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(length=128), nullable=False)
    event_id: Mapped[str] = mapped_column(String(length=128), nullable=False)
    status: Mapped[str] = mapped_column(String(length=64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
