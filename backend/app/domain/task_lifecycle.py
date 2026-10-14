"""Task lifecycle state machine (spec: task_lifecycle).

Pure domain logic - no database dependencies - so it can be unit tested
exhaustively (spec testing_strategy.unit_tests: "Task status transitions")
and reused by the future Task API (Phase 4).
"""

from enum import StrEnum


class TaskStatus(StrEnum):
    draft = "draft"
    open = "open"
    in_progress = "in_progress"
    blocked = "blocked"
    under_review = "under_review"
    completed = "completed"
    cancelled = "cancelled"
    archived = "archived"


# Transitions exactly as specified in task_lifecycle.transitions
ALLOWED_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.draft: frozenset({TaskStatus.open, TaskStatus.cancelled}),
    TaskStatus.open: frozenset(
        {TaskStatus.in_progress, TaskStatus.blocked, TaskStatus.cancelled}
    ),
    TaskStatus.in_progress: frozenset(
        {TaskStatus.blocked, TaskStatus.under_review, TaskStatus.completed, TaskStatus.cancelled}
    ),
    TaskStatus.blocked: frozenset({TaskStatus.in_progress, TaskStatus.cancelled}),
    TaskStatus.under_review: frozenset(
        {TaskStatus.in_progress, TaskStatus.completed, TaskStatus.cancelled}
    ),
    TaskStatus.completed: frozenset({TaskStatus.in_progress, TaskStatus.archived}),
    TaskStatus.cancelled: frozenset({TaskStatus.open, TaskStatus.archived}),
    TaskStatus.archived: frozenset(),
}

# Transitions that require a recorded reason (spec: transition_rules)
REASON_REQUIRED_TRANSITIONS: frozenset[tuple[TaskStatus, TaskStatus]] = frozenset(
    {
        (TaskStatus.completed, TaskStatus.in_progress),  # reopening a completed task
        (TaskStatus.in_progress, TaskStatus.cancelled),
        (TaskStatus.open, TaskStatus.cancelled),
        (TaskStatus.draft, TaskStatus.cancelled),
        (TaskStatus.blocked, TaskStatus.cancelled),
        (TaskStatus.under_review, TaskStatus.cancelled),
    }
)

# Transitions that require an explanation (spec: "Blocked tasks must have an explanation")
EXPLANATION_REQUIRED_TRANSITIONS: frozenset[tuple[TaskStatus, TaskStatus]] = frozenset(
    {
        (TaskStatus.open, TaskStatus.blocked),
        (TaskStatus.in_progress, TaskStatus.blocked),
    }
)


class TransitionError(ValueError):
    """Raised when a status transition is invalid or missing required justification."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


def validate_transition(
    current: TaskStatus | str,
    target: TaskStatus | str,
    *,
    reason: str | None = None,
) -> TaskStatus:
    """Validate a proposed transition. Returns the target status or raises
    TransitionError with a machine-readable code."""
    try:
        current_status = TaskStatus(current)
    except ValueError as exc:
        raise TransitionError(f"Unknown status '{current}'.", code="invalid_status") from exc
    try:
        target_status = TaskStatus(target)
    except ValueError as exc:
        raise TransitionError(f"Unknown status '{target}'.", code="invalid_status") from exc

    allowed = ALLOWED_TRANSITIONS.get(current_status, frozenset())
    if target_status not in allowed:
        raise TransitionError(
            f"Transition from '{current_status.value}' to '{target_status.value}' is not allowed.",
            code="invalid_transition",
        )

    if (current_status, target_status) in REASON_REQUIRED_TRANSITIONS and not (
        reason and reason.strip()
    ):
        raise TransitionError(
            f"A recorded reason is required to move a task from "
            f"'{current_status.value}' to '{target_status.value}'.",
            code="reason_required",
        )

    if (current_status, target_status) in EXPLANATION_REQUIRED_TRANSITIONS and not (
        reason and reason.strip()
    ):
        raise TransitionError(
            "Blocking a task requires an explanation of the blocker.",
            code="blocker_explanation_required",
        )

    return target_status
