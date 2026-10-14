"""Audit service (SEC-005): consistent, transactional audit event writes."""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import AuditEvent, User

logger = logging.getLogger("decops.audit")

# Never record these keys in audit metadata (SEC-005: exclude sensitive content)
SENSITIVE_KEYS = {"password", "token", "session_token", "secret", "authorization"}


def _scrub(payload: dict | None) -> dict | None:
    if not payload:
        return None
    return {
        k: ("[REDACTED]" if any(s in k.lower() for s in SENSITIVE_KEYS) else v)
        for k, v in payload.items()
    }


def record_audit_event(
    db: Session,
    *,
    action: str,
    resource_type: str,
    resource_id: str | uuid.UUID | None = None,
    actor: User | None = None,
    actor_user_id: uuid.UUID | None = None,
    request_id: str | None = None,
    reason: str | None = None,
    change_summary: str | None = None,
    metadata: dict | None = None,
) -> AuditEvent:
    """Append an audit event. The caller is responsible for committing inside
    the same transaction as the business change (atomic audit writes)."""
    resolved_actor_id = actor_user_id if actor_user_id else (actor.id if actor else None)
    event = AuditEvent(
        actor_user_id=resolved_actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else None,
        occurred_at=datetime.now(UTC),
        request_id=request_id,
        reason=reason,
        change_summary=change_summary,
        metadata_json=_scrub(metadata),
    )
    db.add(event)
    logger.info(
        "audit_event",
        extra={
            "context": {
                "action": action,
                "resource_type": resource_type,
                "resource_id": str(resource_id) if resource_id else None,
                "actor_user_id": str(resolved_actor_id) if resolved_actor_id else None,
            }
        },
    )
    return event
