"""Collaboration & notification models (spec data_model, Phase 6).

comments / attachments are nested task resources: they inherit the task's
access policy through the access engine (Operation.COMMENT / Operation.ATTACH)
 - cross-task isolation is structural because every row carries its task_id and
services always load through the owning task.

notifications is the in-app channel state. outbox_events is the transactional
outbox: business transactions append events in the SAME database transaction,
and a background worker delivers them (idempotently, with retries). A rolled
back business transaction therefore never produces a notification.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow
from app.db.types import JSONType, UTCDateTime


class OutboxStatus(str, enum.Enum):
    pending = "pending"                # due (or waiting for next_attempt_at)
    processing = "processing"          # claimed by a worker pass
    processed = "processed"            # delivered to all channels
    permanent_failure = "permanent_failure"  # recorded, never retried


class OutboxEvent(UUIDPrimaryKeyMixin, Base):
    """One business event awaiting delivery (transactional outbox row).

    `payload` carries everything the worker needs at delivery time so it can
    RE-RESOLVE recipients and RE-CHECK authorization against current state
    (spec: "Re-check authorization before sending sensitive task details",
    "A background notification job does not disclose information after access
    revocation").
    """

    __tablename__ = "outbox_events"

    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(30), nullable=False, default="task")
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSONType(), nullable=False, default=dict)

    status: Mapped[OutboxStatus] = mapped_column(
        String(20), default=OutboxStatus.pending, nullable=False, index=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True, index=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class Notification(UUIDPrimaryKeyMixin, Base):
    """A delivered in-app notification for exactly one recipient."""

    __tablename__ = "notifications"
    __table_args__ = (
        # Idempotency: one delivery per (outbox event, recipient) - replaying a
        # claimed event must never duplicate notifications (retry-safe).
        UniqueConstraint("outbox_event_id", "recipient_id", name="uq_notification_delivery"),
        Index("ix_notifications_recipient_created", "recipient_id", "created_at"),
    )

    recipient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(30), nullable=False, default="task")
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    payload: Mapped[dict | None] = mapped_column(JSONType(), nullable=True)
    outbox_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("outbox_events.id", ondelete="SET NULL"), nullable=True
    )
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)

    recipient = relationship("User", foreign_keys=[recipient_id], lazy="joined")


class NotificationPreference(UUIDPrimaryKeyMixin, Base):
    """Per-user, per-event channel switches (spec: respect user notification
    preferences). Missing rows default to enabled on both channels."""

    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", "event_type", name="uq_notification_preference"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    in_app_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    email_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)


class Comment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Task/work-item comment (spec MOD-006). Soft-deleted rows keep the
    audit trail intact but are excluded from listings."""

    __tablename__ = "comments"

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    work_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("work_items.id", ondelete="SET NULL"), index=True, nullable=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    author = relationship("User", foreign_keys=[author_id], lazy="joined")
    work_item = relationship("WorkItem", foreign_keys=[work_item_id])

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class Attachment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Private task attachment. Bytes live under the configured storage dir,
    referenced only by `storage_key` - the key is never exposed through the
    API; downloads stream through an authorization-checked endpoint."""

    __tablename__ = "attachments"

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    work_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("work_items.id", ondelete="SET NULL"), index=True, nullable=True
    )
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False, default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)  # sha256 hex
    scan_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    uploaded_by = relationship("User", foreign_keys=[uploaded_by_id], lazy="joined")
    work_item = relationship("WorkItem", foreign_keys=[work_item_id])

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
