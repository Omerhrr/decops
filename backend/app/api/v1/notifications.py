"""Notification center endpoints : in-app delivery state, read
tracking, per-user channel preferences, and a manual worker trigger for
administrators (useful for ops and demonstrations)."""

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, require_permission
from app.core.errors import NotFoundError, ValidationFailedError
from app.db.base import utcnow
from app.domain.notifications import EventType
from app.models import Notification, NotificationPreference, User
from app.schemas.collaboration import (
    NotificationListOut,
    NotificationOut,
    NotificationPreferenceOut,
    NotificationPreferenceUpdate,
    NotificationPreferencesOut,
    UnreadCountOut,
    WorkerPassOut,
)
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def _auth(request: Request, user: CurrentUser) -> User:
    request.state.user = user
    return user


@router.get("")
def list_notifications(
    request: Request, db: DbSession, user: User = Depends(_auth),
    unread_only: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    stmt = (
        select(Notification)
        .where(Notification.recipient_id == user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
    )
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    items = db.scalars(stmt).all()
    unread = _unread_count(db, user.id)
    return NotificationListOut(
        items=[NotificationOut.model_validate(n) for n in items],
        unread=unread,
    ).model_dump(mode="json")


def _unread_count(db, user_id) -> int:
    return int(db.scalar(
        select(func.count(Notification.id)).where(
            Notification.recipient_id == user_id,
            Notification.read_at.is_(None),
        )
    ) or 0)


@router.get("/unread-count")
def unread_count(request: Request, db: DbSession, user: User = Depends(_auth)) -> dict:
    return UnreadCountOut(unread=_unread_count(db, user.id)).model_dump(mode="json")


@router.post("/read-all")
def read_all(request: Request, db: DbSession, user: User = Depends(_auth)) -> dict:
    updated = db.query(Notification).filter(
        Notification.recipient_id == user.id,
        Notification.read_at.is_(None),
    ).update({"read_at": utcnow()}, synchronize_session=False)
    db.commit()
    return {"updated": updated}


@router.post("/{notification_id}/read")
def mark_read(
    notification_id: uuid.UUID, request: Request, db: DbSession,
    user: User = Depends(_auth),
) -> dict:
    notification = db.get(Notification, notification_id)
    # 404, not 403: never confirm the existence of other users' notifications.
    if notification is None or notification.recipient_id != user.id:
        raise NotFoundError("Notification not found.")
    if notification.read_at is None:
        notification.read_at = utcnow()
        db.commit()
    return NotificationOut.model_validate(notification).model_dump(mode="json")


@router.get("/preferences")
def get_preferences(request: Request, db: DbSession, user: User = Depends(_auth)) -> dict:
    rows = db.scalars(
        select(NotificationPreference).where(NotificationPreference.user_id == user.id)
    ).all()
    return NotificationPreferencesOut(
        preferences=[NotificationPreferenceOut.model_validate(r) for r in rows]
    ).model_dump(mode="json")


@router.put("/preferences")
def update_preference(
    payload: NotificationPreferenceUpdate, request: Request, db: DbSession,
    user: User = Depends(_auth),
) -> dict:
    if payload.event_type not in EventType.ALL:
        raise ValidationFailedError(f"Unknown event type '{payload.event_type}'.")
    pref = db.scalar(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user.id,
            NotificationPreference.event_type == payload.event_type,
        )
    )
    if pref is None:
        pref = NotificationPreference(
            user_id=user.id, event_type=payload.event_type,
            in_app_enabled=payload.in_app_enabled, email_enabled=payload.email_enabled,
        )
        db.add(pref)
    else:
        pref.in_app_enabled = payload.in_app_enabled
        pref.email_enabled = payload.email_enabled
    db.commit()
    db.refresh(pref)
    return NotificationPreferenceOut.model_validate(pref).model_dump(mode="json")


@router.post("/process", dependencies=[Depends(require_permission("tasks.manage_all"))])
def process_now(request: Request, db: DbSession) -> dict:
    """Manual worker tick (admin-gated). The same logic runs automatically in
    the background loop; this endpoint exists for operations and testing."""
    counts = notification_service.worker_pass(db)
    return WorkerPassOut(**counts).model_dump(mode="json")
