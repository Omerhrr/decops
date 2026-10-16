"""Notification domain rules - pure logic.

Event catalog, recipient fan-out defaults, email subject redaction, and retry
backoff live here so they are unit-testable and reusable by the worker.

Security-critical rules encoded:
- The acting user never receives their own event (actor exclusion).
- Email subjects for confidential tasks (private/custom visibility) use the
  task number only - never the title ("Avoid exposing confidential task
  titles in email subjects where policy prohibits it").
- Transient vs permanent delivery failures get different treatment:
  transient -> exponential backoff retry; permanent -> recorded, no retry.
"""

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta


class EventType:
    """Spec notifications.events (+ collaboration-derived events, same family)."""

    TASK_ASSIGNED = "task_assigned"
    SUPPORTING_PM_ADDED = "supporting_pm_added"
    DEADLINE_APPROACHING = "deadline_approaching"
    TASK_OVERDUE = "task_overdue"
    WORK_ITEM_COMPLETED = "work_item_completed"
    TASK_BLOCKED = "task_blocked"
    BLOCKER_RESOLVED = "blocker_resolved"
    TASK_SUBMITTED_FOR_REVIEW = "task_submitted_for_review"
    REVIEW_REJECTED = "review_rejected"
    TASK_COMPLETED = "task_completed"
    TASK_REOPENED = "task_reopened"
    VISIBILITY_CHANGED = "visibility_changed"
    ACCESS_GRANTED = "access_granted"
    ACCESS_REVOKED = "access_revoked"
    MILESTONE_COMPLETED = "milestone_completed"

    ALL = frozenset({
        TASK_ASSIGNED, SUPPORTING_PM_ADDED, DEADLINE_APPROACHING, TASK_OVERDUE,
        WORK_ITEM_COMPLETED, TASK_BLOCKED, BLOCKER_RESOLVED,
        TASK_SUBMITTED_FOR_REVIEW, REVIEW_REJECTED, TASK_COMPLETED,
        TASK_REOPENED, VISIBILITY_CHANGED, ACCESS_GRANTED, ACCESS_REVOKED,
        MILESTONE_COMPLETED,
    })

    # Events directed at exactly one user (the affected user), not the circle.
    TARGETED_EVENTS = frozenset({
        TASK_ASSIGNED, SUPPORTING_PM_ADDED, ACCESS_GRANTED, ACCESS_REVOKED,
    })


# Visibility modes whose task titles count as confidential for email subjects.
CONFIDENTIAL_VISIBILITY_MODES = frozenset({"private", "custom"})


def is_confidential(visibility_mode: str) -> bool:
    return str(visibility_mode) in CONFIDENTIAL_VISIBILITY_MODES


def email_subject(*, event_label: str, task_number: str, task_title: str,
                  visibility_mode: str) -> str:
    """Subject line with title redaction for confidential tasks."""
    if is_confidential(visibility_mode):
        return f"DecOps: {event_label} - task {task_number}"
    return f"DecOps: {event_label} - {task_title} ({task_number})"


def default_circle(
    *,
    actor_id: uuid.UUID | None,
    accountable_pm_id: uuid.UUID | None,
    creator_id: uuid.UUID | None,
    participant_ids: Iterable[uuid.UUID],
) -> set[uuid.UUID]:
    """Default recipient circle for a task event: everyone involved except the
    acting user (you do not get notified about your own action)."""
    circle = set(participant_ids)
    if accountable_pm_id:
        circle.add(accountable_pm_id)
    if creator_id:
        circle.add(creator_id)
    if actor_id:
        circle.discard(actor_id)
    return circle


def targeted_recipients(
    *,
    target_user_id: uuid.UUID | None,
    actor_id: uuid.UUID | None,
) -> set[uuid.UUID]:
    """Recipients for events about a specific user (assignment, grants)."""
    if target_user_id is None:
        return set()
    if actor_id is not None and target_user_id == actor_id:
        return set()  # acting on yourself is not news
    return {target_user_id}


def backoff_delay(attempt_count: int, *, base_seconds: float, cap_seconds: float = 3600.0) -> float:
    """Exponential backoff after the Nth failed attempt (1-based).

    attempt 1 -> base, attempt 2 -> 2*base, attempt 3 -> 4*base ... capped.
    """
    if attempt_count < 1:
        return base_seconds
    return min(base_seconds * (2 ** (attempt_count - 1)), cap_seconds)


def next_attempt_time(*, now: datetime, attempt_count: int, base_seconds: float) -> datetime:
    delay = backoff_delay(attempt_count, base_seconds=base_seconds)
    return now + timedelta(seconds=delay)


class PermanentDeliveryError(Exception):
    """Raised by delivery code when retrying can never succeed (bad payload,
    missing aggregate). The event is recorded as a permanent failure."""


def event_label(event_type: str) -> str:
    labels = {
        EventType.TASK_ASSIGNED: "You were assigned a task",
        EventType.SUPPORTING_PM_ADDED: "A supporting PM was added to your task",
        EventType.DEADLINE_APPROACHING: "Deadline approaching",
        EventType.TASK_OVERDUE: "Task overdue",
        EventType.WORK_ITEM_COMPLETED: "A work item was completed",
        EventType.TASK_BLOCKED: "A task was blocked",
        EventType.BLOCKER_RESOLVED: "A blocker was resolved",
        EventType.TASK_SUBMITTED_FOR_REVIEW: "A task was submitted for review",
        EventType.REVIEW_REJECTED: "A review was rejected",
        EventType.TASK_COMPLETED: "A task was completed",
        EventType.TASK_REOPENED: "A task was reopened",
        EventType.VISIBILITY_CHANGED: "Task visibility changed",
        EventType.ACCESS_GRANTED: "You were granted access to a task",
        EventType.ACCESS_REVOKED: "Your access to a task changed",
        EventType.MILESTONE_COMPLETED: "A milestone was completed",
    }
    return labels.get(event_type, event_type.replace("_", " ").capitalize())


def summary_for_event(event_type: str, *, task_number: str, task_title: str,
                      actor_name: str | None, item_title: str | None = None) -> str:
    """Human-readable notification summary (task number always included -
    titles are fine in-app because the recipient already passed VIEW authz)."""
    who = actor_name or "Someone"
    if event_type == EventType.TASK_ASSIGNED:
        return f"{who} assigned you to {task_number}"
    if event_type == EventType.SUPPORTING_PM_ADDED:
        return f"{who} added you as a supporting PM on {task_number}"
    if event_type == EventType.WORK_ITEM_COMPLETED:
        return f"{who} completed \"{item_title}\" on {task_number} ({task_title})"
    if event_type == EventType.MILESTONE_COMPLETED:
        return f"Milestone \"{item_title}\" completed on {task_number}"
    if event_type == EventType.TASK_BLOCKED:
        return f"{who} blocked {task_number} ({task_title})"
    if event_type == EventType.BLOCKER_RESOLVED:
        return f"\"{item_title}\" on {task_number} is no longer blocked"
    if event_type == EventType.TASK_SUBMITTED_FOR_REVIEW:
        return f"{who} submitted {task_number} ({task_title}) for review"
    if event_type == EventType.REVIEW_REJECTED:
        return f"{who} rejected the review of {task_number} ({task_title})"
    if event_type == EventType.TASK_COMPLETED:
        return f"{who} completed {task_number} ({task_title})"
    if event_type == EventType.TASK_REOPENED:
        return f"{who} reopened {task_number} ({task_title})"
    if event_type == EventType.VISIBILITY_CHANGED:
        return f"{who} changed the visibility of {task_number} ({task_title})"
    if event_type == EventType.ACCESS_GRANTED:
        return f"You were granted access to {task_number} ({task_title})"
    if event_type == EventType.ACCESS_REVOKED:
        return f"Your access to {task_number} changed"
    if event_type == EventType.DEADLINE_APPROACHING:
        return f"{task_number} ({task_title}) is due soon"
    if event_type == EventType.TASK_OVERDUE:
        return f"{task_number} ({task_title}) is overdue"
    return f"{who} updated {task_number}"
