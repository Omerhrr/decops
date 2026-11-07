"""Integration models: personal API tokens, outgoing webhooks, recurring tasks."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import JSONType, UTCDateTime


class ApiToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Personal access token. Acts as its owner with the owner's permissions
    (never more), optionally read-only. Only a SHA-256 hash is stored."""

    __tablename__ = "api_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    prefix: Mapped[str] = mapped_column(String(12))
    scope: Mapped[str] = mapped_column(String(10), default="read")  # read | write
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class Webhook(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Outgoing webhook. Payloads carry ids and numbers only (no titles or
    descriptions) so a subscriber never receives confidential task content."""

    __tablename__ = "webhooks"

    url: Mapped[str] = mapped_column(String(500))
    secret_enc: Mapped[str] = mapped_column(Text)  # Fernet-encrypted signing secret
    events: Mapped[list] = mapped_column(JSONType, default=list)  # [] = all events
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_delivery_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)


class RecurringTask(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Template that spawns a normal task on a schedule."""

    __tablename__ = "recurring_tasks"

    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    accountable_pm_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    visibility_mode: Mapped[str] = mapped_column(String(30), default="participants")
    department_ids: Mapped[list] = mapped_column(JSONType, default=list)
    frequency: Mapped[str] = mapped_column(String(10))  # daily | weekly | monthly
    interval: Mapped[int] = mapped_column(Integer, default=1)
    due_after_days: Mapped[int] = mapped_column(Integer, default=7)
    next_run_on: Mapped[date] = mapped_column(Date)
    last_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
