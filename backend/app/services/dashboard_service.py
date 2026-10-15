"""Dashboard service (MOD-007, Phase 7).

Single source of truth for dashboard aggregates: every number on every
dashboard is computed from `visible_tasks()` — the identical access-engine
evaluation (fresh ActorContext + per-task AccessPolicy, Operation.VIEW) that
gates the task register. This makes "dashboard totals reconcile with
authorized task records" true by construction, and restricted tasks cannot
leak through reports because restricted tasks are simply not in the set.

Personal sections (assigned / accountable / overdue / blocked / upcoming)
further intersect the visible set with the acting user's assignments, so a
user never learns about tasks through their own dashboard either.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.domain import access_policy
from app.domain.access_policy import Operation
from app.domain.task_lifecycle import TaskStatus
from app.models import Task, TaskActivity, TaskAssignment, TaskDepartment, User
from app.services.task_service import build_actor_context, build_policy

# Statuses that represent live work (everything not terminal).
ACTIVE_STATUSES = frozenset(
    {
        TaskStatus.draft,
        TaskStatus.open,
        TaskStatus.in_progress,
        TaskStatus.blocked,
        TaskStatus.under_review,
    }
)
TERMINAL_STATUSES = frozenset(
    {TaskStatus.completed, TaskStatus.cancelled, TaskStatus.archived}
)

DUE_SOON_DAYS = 7
UPCOMING_LIMIT = 8
ACTIVITY_LIMIT = 10
SANDBOX_TASK_CAP = 2000  # matches task_service.list_tasks_for_actor


def _status_of(task: Task) -> TaskStatus:
    value = task.status.value if hasattr(task.status, "value") else str(task.status)
    return TaskStatus(value)


def visible_tasks(db: Session, actor: User) -> list[Task]:
    """All tasks the actor may VIEW (fresh authorization state, same engine as
    the register). Ordered newest-first; capped for sandbox scale."""
    actor_ctx = build_actor_context(db, actor)
    candidates = db.scalars(
        select(Task)
        .options(
            joinedload(Task.accountable_pm),
            joinedload(Task.task_departments).joinedload(TaskDepartment.department),
        )
        .order_by(Task.created_at.desc())
        .limit(SANDBOX_TASK_CAP)
    ).unique().all()
    return [
        t for t in candidates
        if access_policy.evaluate_access(actor_ctx, build_policy(db, t), Operation.VIEW)
        is access_policy.AccessDecision.ALLOW
    ]


def _is_active(task: Task) -> bool:
    return _status_of(task) in ACTIVE_STATUSES


def _is_overdue(task: Task, today: date) -> bool:
    return _is_active(task) and task.due_date is not None and task.due_date < today


def _my_assignment_task_ids(db: Session, user: User) -> set[uuid.UUID]:
    rows = db.scalars(
        select(TaskAssignment.task_id).where(
            TaskAssignment.user_id == user.id,
            TaskAssignment.revoked_at.is_(None),
            TaskAssignment.assignment_role.in_(["accountable_pm", "supporting_pm"]),
        )
    ).all()
    return set(rows)


def personal_summary(db: Session, actor: User, visible: list[Task]) -> dict:
    today = datetime.now(UTC).date()
    assigned_ids = _my_assignment_task_ids(db, actor)
    mine = [t for t in visible if t.id in assigned_ids or t.accountable_pm_id == actor.id]
    return {
        "assigned_active": sum(1 for t in mine if t.id in assigned_ids and _is_active(t)),
        "accountable_active": sum(
            1 for t in mine if t.accountable_pm_id == actor.id and _is_active(t)
        ),
        "overdue": sum(1 for t in mine if _is_overdue(t, today)),
        "blocked": sum(1 for t in mine if _status_of(t) is TaskStatus.blocked),
        "due_soon": sum(
            1 for t in mine
            if _is_active(t) and t.due_date is not None
            and today <= t.due_date <= today + timedelta(days=DUE_SOON_DAYS)
        ),
    }


def status_breakdown(visible: list[Task]) -> dict:
    counts = {s.value: 0 for s in TaskStatus}
    for t in visible:
        counts[_status_of(t).value] += 1
    return counts


def deadline_row(task: Task) -> dict:
    today = datetime.now(UTC).date()
    pm = task.accountable_pm
    return {
        "task_id": task.id,
        "task_number": task.task_number,
        "title": task.title,
        "due_date": task.due_date,
        "days_left": (task.due_date - today).days,
        "status": _status_of(task).value,
        "priority": (task.priority.value if hasattr(task.priority, "value") else str(task.priority)),
        "accountable_pm": pm,
    }


def _activity_rows(db: Session, visible: list[Task]) -> list[dict]:
    """Latest user-facing activity across the authorized task set only."""
    if not visible:
        return []
    ids = [t.id for t in visible]
    by_id = {t.id: t for t in visible}
    events = db.scalars(
        select(TaskActivity)
        .options(joinedload(TaskActivity.actor))
        .where(TaskActivity.task_id.in_(ids))
        .order_by(TaskActivity.created_at.desc())
        .limit(ACTIVITY_LIMIT)
    ).all()
    rows = []
    for e in events:
        t = by_id[e.task_id]
        rows.append({
            "task_id": t.id,
            "task_number": t.task_number,
            "task_title": t.title,
            "activity_type": e.activity_type,
            "summary": e.summary,
            "actor": e.actor,
            "created_at": e.created_at,
        })
    return rows


def management_overview(visible: list[Task]) -> dict:
    """Company-wide aggregates for dashboards.view holders. Computed from the
    same visible set, so it reconciles with the administrator's authorized
    register (tasks.manage_all => entire register)."""
    today = datetime.now(UTC).date()
    week_ago = datetime.now(UTC) - timedelta(days=7)
    counts = status_breakdown(visible)
    active = sum(counts[s.value] for s in ACTIVE_STATUSES)
    completed = counts["completed"]
    denominator = active + completed
    completed_at_attr = [
        t.completed_at for t in visible if _status_of(t) is TaskStatus.completed and t.completed_at
    ]
    completed_this_week = sum(1 for c in completed_at_attr if c >= week_ago)
    overdue = sum(1 for t in visible if _is_overdue(t, today))
    return {
        "total_visible": len(visible),
        "active": active,
        "overdue": overdue,
        "blocked": counts["blocked"],
        "completion_rate": round(100 * completed / denominator) if denominator else 0,
        "completed_this_week": completed_this_week,
        "by_status": counts,
    }


def dashboard_summary(db: Session, actor: User, *, include_management: bool) -> dict:
    visible = visible_tasks(db, actor)
    today = datetime.now(UTC).date()

    upcoming = sorted(
        (t for t in visible if _is_active(t) and t.due_date is not None
         and today <= t.due_date <= today + timedelta(days=30)),
        key=lambda t: (t.due_date, t.task_number),
    )[:UPCOMING_LIMIT]
    blocked = [t for t in visible if _status_of(t) is TaskStatus.blocked][:UPCOMING_LIMIT]
    counts = status_breakdown(visible)

    summary = {
        "me": personal_summary(db, actor, visible),
        "visible_totals": counts,
        "visible_total": len(visible),
        "overdue_total": sum(1 for t in visible if _is_overdue(t, today)),
        "blocked_total": counts["blocked"],
        "upcoming_deadlines": [deadline_row(t) for t in upcoming],
        "blocked_tasks": [deadline_row(t) for t in blocked],
        "recent_activity": _activity_rows(db, visible),
        "management_overview": management_overview(visible) if include_management else None,
    }
    return summary


def my_tasks(
    db: Session,
    actor: User,
    *,
    scope: str = "assigned",
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[Task], int]:
    """Visible tasks where I am an active assignee (assigned) or the
    accountable PM (accountable). `all` unions both roles."""
    visible = visible_tasks(db, actor)
    assigned_ids = _my_assignment_task_ids(db, actor)
    if scope == "assigned":
        mine = [t for t in visible if t.id in assigned_ids]
    elif scope == "accountable":
        mine = [t for t in visible if t.accountable_pm_id == actor.id]
    elif scope == "all":
        mine = [
            t for t in visible
            if t.id in assigned_ids or t.accountable_pm_id == actor.id
        ]
    else:
        raise ValueError(f"Unknown scope '{scope}'.")
    total = len(mine)
    start = (max(page, 1) - 1) * page_size
    return mine[start:start + page_size], total


def overdue_tasks(db: Session, actor: User) -> list[Task]:
    today = datetime.now(UTC).date()
    visible = visible_tasks(db, actor)
    return sorted(
        (t for t in visible if _is_overdue(t, today)),
        key=lambda t: (t.due_date, t.task_number),
    )


def blocked_tasks(db: Session, actor: User) -> list[Task]:
    visible = visible_tasks(db, actor)
    return [t for t in visible if _status_of(t) is TaskStatus.blocked]
