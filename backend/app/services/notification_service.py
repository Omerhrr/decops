"""Notification service (Phase 6): transactional outbox + delivery.

Producer side (runs inside business transactions):
- record_event() appends an outbox_events row in the SAME database
  transaction as the business change. If the transaction rolls back, the
  event never existed — "Do not send notifications for transactions that
  ultimately roll back" (spec delivery_requirements).

Consumer side (background worker, own sessions, one commit per event):
- process_due_events() claims due events, re-resolves recipients from
  CURRENT state, re-checks task authorization per recipient (revoked access
  never discloses information), respects per-user preferences, de-duplicates
  deliveries via the (outbox_event_id, recipient_id) unique constraint, and
  delivers in-app + optional email.
- Failures are classified: transient -> exponential backoff retry;
  permanent -> recorded with last_error and never retried.
- Processing is idempotent: replaying an event cannot duplicate
  notifications (DB-level unique constraint + sent-set checks).

The deadline sweep (deadline_approaching / task_overdue) is also part of the
worker pass and is de-duplicated per (recipient, event, task, time window).
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain import access_policy, notifications as ntf
from app.models import Notification, NotificationPreference, OutboxEvent, OutboxStatus, Task, User
from app.services import email_sender
from app.services.task_service import build_actor_context, build_policy

logger = logging.getLogger("decops.notifications")


# ---------------------------------------------------------------------------
# Producer API (call inside the business transaction)
# ---------------------------------------------------------------------------

def record_event(
    db: Session,
    *,
    event_type: str,
    task_id: uuid.UUID,
    actor: User | None = None,
    target_user_id: uuid.UUID | None = None,
    work_item_id: uuid.UUID | None = None,
    extra: dict | None = None,
) -> OutboxEvent | None:
    """Append an outbox event in the caller's transaction. Never raises on
    bad input: a notification problem must never break the business change."""
    if not settings.outbox_worker_enabled and not settings.email_notifications_enabled:
        # Outbox disabled entirely (rare, e.g. stripped deployments).
        pass
    try:
        payload: dict = {
            "actor_id": str(actor.id) if actor else None,
            "actor_name": actor.full_name if actor else None,
            "target_user_id": str(target_user_id) if target_user_id else None,
            "work_item_id": str(work_item_id) if work_item_id else None,
        }
        if extra:
            payload.update(extra)
        event = OutboxEvent(
            event_type=event_type,
            aggregate_type="task",
            aggregate_id=str(task_id),
            payload=payload,
            status=OutboxStatus.pending,
            next_attempt_at=datetime.now(UTC),
        )
        db.add(event)
        return event
    except Exception:  # pragma: no cover - defensive: notifications never break business flow
        logger.exception("Failed to enqueue notification event %s", event_type)
        return None


# ---------------------------------------------------------------------------
# Preference resolution
# ---------------------------------------------------------------------------

def load_preferences(db: Session, user_id: uuid.UUID) -> dict[str, NotificationPreference]:
    return {
        p.event_type: p
        for p in db.scalars(
            select(NotificationPreference).where(NotificationPreference.user_id == user_id)
        ).all()
    }


def wants(db: Session, user_id: uuid.UUID, event_type: str, channel: str) -> bool:
    """Channel decision honoring per-user preferences (default: enabled)."""
    pref = db.scalar(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.event_type == event_type,
        )
    )
    if pref is None:
        return True
    return bool(pref.in_app_enabled) if channel == "in_app" else bool(pref.email_enabled)


# ---------------------------------------------------------------------------
# Delivery (worker side)
# ---------------------------------------------------------------------------

def _task_circle(db: Session, task: Task) -> set[uuid.UUID]:
    participant_ids = {a.user_id for a in task.assignments if a.revoked_at is None}
    return ntf.default_circle(
        actor_id=None,
        accountable_pm_id=task.accountable_pm_id,
        creator_id=task.created_by_id,
        participant_ids=participant_ids,
    )


def _recipients_for(db: Session, event: OutboxEvent, task: Task) -> set[uuid.UUID]:
    """Resolve recipients from CURRENT state at delivery time."""
    actor_id = event.payload.get("actor_id")
    actor_uuid = uuid.UUID(actor_id) if actor_id else None
    target = event.payload.get("target_user_id")
    target_uuid = uuid.UUID(target) if target else None

    if event.event_type in ntf.EventType.TARGETED_EVENTS:
        return ntf.targeted_recipients(target_user_id=target_uuid, actor_id=actor_uuid)

    circle = _task_circle(db, task)
    if event.event_type == ntf.EventType.TASK_OVERDUE or event.event_type == ntf.EventType.DEADLINE_APPROACHING:
        # Sweep-generated events carry no actor.
        return circle
    if actor_uuid:
        circle.discard(actor_uuid)
    return circle


def _can_see_task(db: Session, user_id: uuid.UUID, task: Task) -> bool:
    """Re-check authorization at delivery time (revocation-safe delivery)."""
    user = db.get(User, user_id)
    if user is None or str(getattr(user.account_status, "value", user.account_status)) != "active":
        return False
    try:
        access_policy.require_access(
            build_actor_context(db, user), build_policy(db, task), access_policy.Operation.VIEW,
        )
    except access_policy.AccessDeniedError:
        return False
    return True


def _deliver_in_app(db: Session, event: OutboxEvent, task: Task, recipient_id: uuid.UUID) -> bool:
    if not wants(db, recipient_id, event.event_type, "in_app"):
        return False
    existing = db.scalar(
        select(Notification).where(
            Notification.outbox_event_id == event.id,
            Notification.recipient_id == recipient_id,
        )
    )
    if existing is not None:
        return False  # idempotent replay
    summary = ntf.summary_for_event(
        event.event_type,
        task_number=task.task_number,
        task_title=task.title,
        actor_name=event.payload.get("actor_name"),
    )
    db.add(Notification(
        recipient_id=recipient_id,
        event_type=event.event_type,
        resource_type="task",
        resource_id=str(task.id),
        payload={
            "title": ntf.event_label(event.event_type),
            "summary": summary,
            "task_number": task.task_number,
        },
        outbox_event_id=event.id,
    ))
    return True


def _deliver_email(db: Session, event: OutboxEvent, task: Task, recipient_id: uuid.UUID) -> bool:
    if not settings.email_notifications_enabled:
        return False
    if not wants(db, recipient_id, event.event_type, "email"):
        return False
    user = db.get(User, recipient_id)
    if user is None:
        return False
    emailed = set(event.payload.get("emailed_to") or [])
    if str(recipient_id) in emailed:
        return False
    subject = ntf.email_subject(
        event_label=ntf.event_label(event.event_type),
        task_number=task.task_number,
        task_title=task.title,
        visibility_mode=str(getattr(task.visibility_mode, "value", task.visibility_mode)),
    )
    body = (
        event.payload.get("summary")
        or ntf.summary_for_event(
            event.event_type, task_number=task.task_number, task_title=task.title,
            actor_name=event.payload.get("actor_name"),
        )
    )
    email_sender.send_email(to_email=user.email, subject=subject, body=body)
    emailed.add(str(recipient_id))
    event.payload = {**event.payload, "emailed_to": sorted(emailed)}
    return True


def process_event(db: Session, event: OutboxEvent, *, now: datetime | None = None) -> str:
    """Deliver one outbox event. Returns 'processed', 'retry', or 'permanent'.

    The caller owns the commit; a crash before commit leaves the event
    claimed-but-uncommitted, i.e. effectively still pending (retry-safe).
    """
    now = now or datetime.now(UTC)
    event.status = OutboxStatus.processing
    try:
        try:
            task_id = uuid.UUID(event.aggregate_id)
        except (ValueError, TypeError) as exc:
            raise ntf.PermanentDeliveryError(f"Malformed aggregate id: {event.aggregate_id}") from exc

        task = db.get(Task, task_id)
        if task is None:
            raise ntf.PermanentDeliveryError("Task no longer exists; nothing to notify about.")

        recipients = sorted(_recipients_for(db, event, task))
        in_app_created = 0
        emails_sent = 0
        for recipient_id in recipients:
            # Security gate FIRST: revoked access never receives disclosure.
            if not _can_see_task(db, recipient_id, task):
                continue
            if _deliver_in_app(db, event, task, recipient_id):
                in_app_created += 1
            try:
                if _deliver_email(db, event, task, recipient_id):
                    emails_sent += 1
            except email_sender.EmailError as exc:
                # Email is a best-effort channel: record and continue; the
                # failure stays on the event for the next pass via last_error.
                logger.warning("Email delivery failed for event %s: %s", event.id, exc)
                event.last_error = f"email: {exc}"

        event.status = OutboxStatus.processed
        event.processed_at = now
        event.last_error = event.last_error if emails_sent == 0 and event.last_error else None
        logger.info(
            "outbox_event_processed",
            extra={"context": {"event": str(event.id), "type": event.event_type,
                               "in_app": in_app_created, "emails": emails_sent}},
        )
        return "processed"

    except ntf.PermanentDeliveryError as exc:
        event.status = OutboxStatus.permanent_failure
        event.last_error = str(exc)
        event.attempt_count += 1
        return "permanent"

    except Exception as exc:  # transient: schedule retry with backoff
        event.attempt_count += 1
        if event.attempt_count >= settings.outbox_max_attempts:
            event.status = OutboxStatus.permanent_failure
            event.last_error = f"max attempts reached: {exc}"
            return "permanent"
        event.status = OutboxStatus.pending
        event.next_attempt_at = ntf.next_attempt_time(
            now=now, attempt_count=event.attempt_count,
            base_seconds=settings.outbox_base_backoff_seconds,
        )
        event.last_error = str(exc)
        return "retry"


def claim_due_events(db: Session, *, now: datetime, limit: int = 50) -> list[OutboxEvent]:
    stmt = (
        select(OutboxEvent)
        .where(
            OutboxEvent.status.in_([OutboxStatus.pending, OutboxStatus.processing]),
            OutboxEvent.next_attempt_at <= now,
        )
        .order_by(OutboxEvent.created_at.asc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def process_due_events(db: Session, *, now: datetime | None = None, limit: int = 50) -> dict:
    """One worker pass: process due events, committing per event so a single
    bad event cannot block the queue. Returns counters for logging/tests."""
    now = now or datetime.now(UTC)
    events = claim_due_events(db, now=now, limit=limit)
    counts = {"processed": 0, "retry": 0, "permanent": 0, "claimed": len(events)}
    for event in events:
        result = process_event(db, event, now=now)
        counts[result] = counts.get(result, 0) + 1
        db.commit()
    return counts


# ---------------------------------------------------------------------------
# Deadline sweep (deadline_approaching / task_overdue)
# ---------------------------------------------------------------------------

_ACTIVE_STATUSES = ("open", "in_progress", "blocked", "under_review")


def _recently_notified(db: Session, recipient_id: uuid.UUID, event_type: str,
                       task_id: uuid.UUID, *, now: datetime, window_hours: int) -> bool:
    threshold = now - timedelta(hours=window_hours)
    return db.scalar(
        select(Notification.id).where(
            Notification.recipient_id == recipient_id,
            Notification.event_type == event_type,
            Notification.resource_id == str(task_id),
            Notification.created_at >= threshold,
        )
    ) is not None


def sweep_deadlines(db: Session, *, now: datetime | None = None) -> dict:
    """Notify upcoming/overdue deadlines once per dedup window per recipient."""
    now = now or datetime.now(UTC)
    today = now.date()
    horizon = today + timedelta(days=settings.deadline_reminder_days)
    tasks = db.scalars(
        select(Task).where(
            Task.status.in_(_ACTIVE_STATUSES),
            Task.due_date.is_not(None),
            Task.due_date <= horizon,
        )
    ).all()
    created = 0
    skipped = 0
    for task in tasks:
        overdue = task.due_date < today
        event_type = ntf.EventType.TASK_OVERDUE if overdue else ntf.EventType.DEADLINE_APPROACHING
        task_mode = str(getattr(task.visibility_mode, "value", task.visibility_mode))
        for recipient_id in sorted(_task_circle(db, task)):
            user = db.get(User, recipient_id)
            if user is None:
                continue
            if not _can_see_task(db, recipient_id, task):
                continue
            if not wants(db, recipient_id, event_type, "in_app"):
                continue
            if _recently_notified(db, recipient_id, event_type, task.id,
                                  now=now, window_hours=settings.deadline_dedup_hours):
                skipped += 1
                continue
            db.add(Notification(
                recipient_id=recipient_id,
                event_type=event_type,
                resource_type="task",
                resource_id=str(task.id),
                payload={
                    "title": ntf.event_label(event_type),
                    "summary": ntf.summary_for_event(
                        event_type, task_number=task.task_number, task_title=task.title,
                        actor_name=None,
                    ),
                    "task_number": task.task_number,
                },
            ))
            created += 1
        if overdue and task_mode not in ntf.CONFIDENTIAL_VISIBILITY_MODES:
            pass  # visibility retained for potential email escalation later
    if created:
        db.commit()
    return {"created": created, "skipped": skipped, "tasks_scanned": len(tasks)}


def worker_pass(db: Session, *, now: datetime | None = None) -> dict:
    """Full worker tick: outbox delivery first, then the deadline sweep."""
    now = now or datetime.now(UTC)
    counts = process_due_events(db, now=now)
    sweep = sweep_deadlines(db, now=now)
    counts["deadline_created"] = sweep["created"]
    return counts
