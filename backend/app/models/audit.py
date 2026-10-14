"""Audit event model (spec data_model: audit_events, SEC-005 Auditability).

Audit events are append-only from the application: no update or delete
operations are ever issued against this table.
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin, utcnow
from app.db.types import UTCDateTime
from app.db.types import JSONType


class AuditEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_events"

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, nullable=False, index=True
    )
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
