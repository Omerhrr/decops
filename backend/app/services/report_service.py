"""Reporting service (MOD-007, Phase 7): authorized trends, workload, exports.

Authorization model (spec RBAC matrix):
- task-completion  -> reports.view (Management); aggregates over the actor's
  engine-visible tasks only.
- department-workload -> reports.view (all departments) OR
  reports.department.view (Department Lead: only departments they lead or
  belong to); per-department task counts count ONLY engine-visible tasks.
- exports -> exports.approved (Read-Only Auditor); every row is re-checked
  against the access engine, and the export action itself is audited.

CSV cells are formula-injection sanitized (SEC: no =/+/@-prefixed payload can
execute when the file opens in a spreadsheet).
"""

import csv
import io
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import ValidationFailedError
from app.domain import access_policy
from app.domain.task_lifecycle import TaskStatus
from app.models import Department, Task, TaskAssignment, TaskDepartment, User, WorkItem, WorkItemType
from app.services.dashboard_service import (
    ACTIVE_STATUSES,
    _is_active,
    _is_overdue,
    _status_of,
    visible_tasks,
)
from app.services.task_service import build_actor_context, build_policy

REPORT_VIEW_PERMISSION = "reports.view"
DEPARTMENT_REPORT_PERMISSION = "reports.department.view"
EXPORT_PERMISSION = "exports.approved"

WEEK_WINDOW_DEFAULT = 12


# ---------------------------------------------------------------------------
# Task completion report
# ---------------------------------------------------------------------------

def task_completion_report(db: Session, actor: User, *, weeks: int = WEEK_WINDOW_DEFAULT) -> dict:
    visible = visible_tasks(db, actor)
    today = datetime.now(UTC).date()
    # Weeks start on Monday; window covers the current week too.
    current_week_start = today - timedelta(days=today.weekday())
    window_start = current_week_start - timedelta(weeks=weeks - 1)

    buckets: dict[date, dict[str, int]] = {
        window_start + timedelta(weeks=i): {"completed": 0, "created": 0}
        for i in range(weeks)
    }
    durations_days: list[float] = []
    for t in visible:
        created_day = t.created_at.date() if t.created_at else None
        if created_day and created_day >= window_start:
            week = created_day - timedelta(days=created_day.weekday())
            if week in buckets:
                buckets[week]["created"] += 1
        if _status_of(t) is TaskStatus.completed and t.completed_at:
            completed_day = t.completed_at.date()
            if completed_day >= window_start:
                week = completed_day - timedelta(days=completed_day.weekday())
                if week in buckets:
                    buckets[week]["completed"] += 1
            if t.created_at:
                durations_days.append((t.completed_at - t.created_at).total_seconds() / 86400)

    series = [
        {"week_start": day, "completed": v["completed"], "created": v["created"]}
        for day, v in sorted(buckets.items())
    ]

    counts = {s.value: 0 for s in TaskStatus}
    for t in visible:
        counts[_status_of(t).value] += 1
    active = sum(counts[s.value] for s in ACTIVE_STATUSES)

    # Milestone progress across authorized tasks (MOD-007 "Milestone progress")
    milestone_rows = db.scalars(
        select(WorkItem).where(
            WorkItem.task_id.in_([t.id for t in visible]) if visible else False,
            WorkItem.item_type == WorkItemType.milestone,
            WorkItem.parent_work_item_id.is_(None),
        )
    ).all()
    milestone_progress = {"total": len(milestone_rows), "completed": 0, "in_progress": 0,
                          "pending": 0, "cancelled": 0}
    for m in milestone_rows:
        status = m.status.value if hasattr(m.status, "value") else str(m.status)
        milestone_progress[status] = milestone_progress.get(status, 0) + 1

    # Blocker analysis: where is work stuck?
    by_priority: dict[str, int] = {}
    by_department: dict[str, int] = {}
    blocked = [t for t in visible if _status_of(t) is TaskStatus.blocked]
    for t in blocked:
        p = t.priority.value if hasattr(t.priority, "value") else str(t.priority)
        by_priority[p] = by_priority.get(p, 0) + 1
        for td in t.task_departments:
            name = td.department.name if td.department else "Unknown"
            by_department[name] = by_department.get(name, 0) + 1

    return {
        "weeks": weeks,
        "series": series,
        "totals": {
            "visible_total": len(visible),
            "active": active,
            "completed": counts["completed"],
            "overdue": sum(1 for t in visible if _is_overdue(t, today)),
            "completed_in_window": sum(w["completed"] for w in buckets.values()),
            "created_in_window": sum(w["created"] for w in buckets.values()),
        },
        "avg_days_to_complete": (
            round(sum(durations_days) / len(durations_days), 1) if durations_days else None
        ),
        "by_status": counts,
        "milestone_progress": milestone_progress,
        "blocker_analysis": {
            "blocked_total": len(blocked),
            "by_priority": by_priority,
            "by_department": by_department,
            "overdue_blocked": sum(1 for t in blocked if _is_overdue(t, today)),
        },
    }


# ---------------------------------------------------------------------------
# Department workload report
# ---------------------------------------------------------------------------

def _reportable_departments(db: Session, actor: User, *, management_scope: bool) -> list[Department]:
    if management_scope:  # reports.view -> every department
        return list(db.scalars(select(Department).order_by(Department.name)).all())
    # Department Lead: departments they lead or belong to
    return sorted(
        {m.department for m in actor.memberships if m.department is not None},
        key=lambda d: d.name,
    )


def department_workload_report(
    db: Session, actor: User, *, management_scope: bool
) -> dict:
    visible = visible_tasks(db, actor)
    today = datetime.now(UTC).date()
    visible_by_dept: dict[uuid.UUID, list[Task]] = {}
    for t in visible:
        for td in t.task_departments:
            visible_by_dept.setdefault(td.department_id, []).append(t)

    # Active (non-revoked) assignments per user over visible tasks only.
    assignment_counts: dict[uuid.UUID, int] = {}
    if visible:
        rows = db.execute(
            select(TaskAssignment.user_id, TaskAssignment.task_id).where(
                TaskAssignment.revoked_at.is_(None),
                TaskAssignment.task_id.in_([t.id for t in visible]),
            )
        ).all()
        visible_ids = {t.id for t in visible}
        for user_id, task_id in rows:
            if task_id in visible_ids:
                assignment_counts[user_id] = assignment_counts.get(user_id, 0) + 1

    departments = _reportable_departments(db, actor, management_scope=management_scope)
    rows = []
    for d in departments:
        tasks = visible_by_dept.get(d.id, [])
        active_tasks = [t for t in tasks if _is_active(t)]
        member_ids = {m.user_id for m in d.memberships}
        rows.append({
            "department_id": d.id,
            "department_name": d.name,
            "lead": d.lead.full_name if d.lead else None,
            "member_count": len(member_ids),
            "active_tasks": len(active_tasks),
            "overdue_tasks": sum(1 for t in tasks if _is_overdue(t, today)),
            "blocked_tasks": sum(1 for t in tasks if _status_of(t) is TaskStatus.blocked),
            "completed_tasks": sum(1 for t in tasks if _status_of(t) is TaskStatus.completed),
            "open_assignments": sum(assignment_counts.get(u, 0) for u in member_ids),
        })
    return {"departments": rows, "scope": "all" if management_scope else "my_departments"}


def department_workspace(db: Session, actor: User, department: Department) -> dict:
    """Department Workspace page payload (spec frontend_pages.Department
    Workspace): authorized departmental tasks, workload, blocked work,
    upcoming deadlines, team assignments."""
    today = datetime.now(UTC).date()
    actor_ctx = build_actor_context(db, actor)
    tasks = [
        t for t in visible_tasks(db, actor)
        if any(td.department_id == department.id for td in t.task_departments)
    ]
    active = [t for t in tasks if _is_active(t)]
    blocked = [t for t in active if _status_of(t) is TaskStatus.blocked]
    upcoming = sorted(
        (t for t in active if t.due_date is not None and today <= t.due_date),
        key=lambda t: (t.due_date, t.task_number),
    )[:10]
    overdue = sorted(
        (t for t in tasks if _is_overdue(t, today)),
        key=lambda t: (t.due_date, t.task_number),
    )[:10]

    visible_ids = {t.id for t in tasks}
    team: dict[uuid.UUID, dict] = {}
    for m in department.memberships:
        team[m.user_id] = {
            "user": m.user,
            "membership_role": (m.membership_role.value
                                if hasattr(m.membership_role, "value") else str(m.membership_role)),
            "open_assignments": 0,
        }
    if visible_ids:
        rows = db.scalars(
            select(TaskAssignment.user_id).where(
                TaskAssignment.revoked_at.is_(None),
                TaskAssignment.task_id.in_(list(visible_ids)),
            )
        ).all()
        for user_id in rows:
            if user_id in team:
                team[user_id]["open_assignments"] += 1

    return {
        "department": {
            "id": department.id,
            "name": department.name,
            "description": department.description,
            "lead": department.lead.full_name if department.lead else None,
            "member_count": len({m.user_id for m in department.memberships}),
        },
        "tasks": [
            {
                "id": t.id,
                "task_number": t.task_number,
                "title": t.title,
                "status": _status_of(t).value,
                "priority": (t.priority.value if hasattr(t.priority, "value") else str(t.priority)),
                "due_date": t.due_date,
                "percent_complete": t.percent_complete,
                "accountable_pm": (t.accountable_pm.full_name if t.accountable_pm else None),
            }
            for t in tasks
        ],
        "active_total": len(active),
        "blocked": [
            {
                "id": t.id,
                "task_number": t.task_number,
                "title": t.title,
                "due_date": t.due_date,
                "accountable_pm": (t.accountable_pm.full_name if t.accountable_pm else None),
            }
            for t in blocked
        ],
        "upcoming": [
            {
                "id": t.id,
                "task_number": t.task_number,
                "title": t.title,
                "due_date": t.due_date,
                "accountable_pm": (t.accountable_pm.full_name if t.accountable_pm else None),
            }
            for t in upcoming
        ],
        "overdue": [
            {
                "id": t.id,
                "task_number": t.task_number,
                "title": t.title,
                "due_date": t.due_date,
                "accountable_pm": (t.accountable_pm.full_name if t.accountable_pm else None),
            }
            for t in overdue
        ],
        "team": [
            {
                "user": {
                    "id": r["user"].id,
                    "full_name": r["user"].full_name,
                    "email": r["user"].email,
                    "employee_code": r["user"].employee_code,
                },
                "membership_role": r["membership_role"],
                "open_assignments": r["open_assignments"],
            }
            for r in sorted(
                team.values(),
                key=lambda r: (-r["open_assignments"], r["user"].full_name),
            )
        ],
    }


# ---------------------------------------------------------------------------
# CSV exports (authorized; audited upstream in the API layer)
# ---------------------------------------------------------------------------

_FORMULA_PREFIXES = ("=", "+", "@", "\t", "\r")


def _csv_safe(value) -> str:
    """Neutralize spreadsheet formula injection on export."""
    text = "" if value is None else str(value)
    if text.startswith(_FORMULA_PREFIXES):
        return "'" + text
    return text


def _fmt_date(d: date | None) -> str:
    return d.isoformat() if d else ""


def _task_row(task: Task) -> dict[str, str]:
    pm = task.accountable_pm
    status = _status_of(task).value
    today = datetime.now(UTC).date()
    return {
        "task_number": task.task_number,
        "title": task.title,
        "status": status,
        "priority": (task.priority.value if hasattr(task.priority, "value") else str(task.priority)),
        "accountable_pm": pm.full_name if pm else "",
        "accountable_pm_email": pm.email if pm else "",
        "departments": "; ".join(
            td.department.name for td in task.task_departments if td.department
        ),
        "start_date": _fmt_date(task.start_date),
        "due_date": _fmt_date(task.due_date),
        "percent_complete": str(task.percent_complete),
        "overdue": "yes" if _is_overdue(task, today) else "no",
        "visibility_mode": task.visibility_mode,
    }


TASK_REGISTER_COLUMNS = [
    "task_number", "title", "status", "priority", "accountable_pm",
    "accountable_pm_email", "departments", "start_date", "due_date",
    "percent_complete", "overdue", "visibility_mode",
]


def task_register_row(task: Task) -> dict[str, str]:
    """Public row builder (CSV and PDF exports share the same field values)."""
    return _task_row(task)


def filter_visible_tasks(
    db: Session,
    actor: User,
    *,
    status: str | None = None,
    priority: str | None = None,
    department_id: uuid.UUID | None = None,
    q: str | None = None,
) -> list[Task]:
    """Engine-visible tasks with the shared register filters (CSV and PDF exports)."""
    visible = visible_tasks(db, actor)

    if status:
        try:
            wanted = TaskStatus(status)
        except ValueError as exc:
            raise ValidationFailedError(f"Unknown status '{status}'.") from exc
        visible = [t for t in visible if _status_of(t) is wanted]
    if priority:
        wanted_p = priority.strip().lower()
        visible = [
            t for t in visible
            if (t.priority.value if hasattr(t.priority, "value") else str(t.priority)) == wanted_p
        ]
    if department_id:
        visible = [
            t for t in visible
            if any(td.department_id == department_id for td in t.task_departments)
        ]
    if q:
        needle = q.strip().lower()
        visible = [
            t for t in visible
            if needle in t.title.lower() or needle in t.task_number.lower()
        ]
    return visible


def export_task_register(
    db: Session,
    actor: User,
    *,
    status: str | None = None,
    priority: str | None = None,
    department_id: uuid.UUID | None = None,
    q: str | None = None,
) -> tuple[str, int]:
    """CSV of the authorized task register (same engine as the register UI)."""
    visible = filter_visible_tasks(
        db, actor, status=status, priority=priority, department_id=department_id, q=q
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(TASK_REGISTER_COLUMNS)
    for t in visible:
        row = _task_row(t)
        writer.writerow([_csv_safe(row[c]) for c in TASK_REGISTER_COLUMNS])
    return buffer.getvalue(), len(visible)


def export_department_workload(db: Session, actor: User, *, management_scope: bool) -> tuple[str, int]:
    report = department_workload_report(db, actor, management_scope=management_scope)
    columns = [
        "department", "lead", "member_count", "active_tasks", "overdue_tasks",
        "blocked_tasks", "completed_tasks", "open_assignments",
    ]
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    for r in report["departments"]:
        writer.writerow([
            _csv_safe(r["department_name"]),
            _csv_safe(r["lead"] or ""),
            r["member_count"], r["active_tasks"], r["overdue_tasks"],
            r["blocked_tasks"], r["completed_tasks"], r["open_assignments"],
        ])
    return buffer.getvalue(), len(report["departments"])


def export_task_completion(db: Session, actor: User, *, weeks: int = WEEK_WINDOW_DEFAULT) -> tuple[str, int]:
    report = task_completion_report(db, actor, weeks=weeks)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["week_start", "completed", "created"])
    for point in report["series"]:
        writer.writerow([
            point["week_start"].isoformat(), point["completed"], point["created"],
        ])
    writer.writerow([])
    writer.writerow(["metric", "value"])
    for key, value in report["totals"].items():
        writer.writerow([_csv_safe(key), value])
    writer.writerow(["avg_days_to_complete", report["avg_days_to_complete"] if report["avg_days_to_complete"] is not None else ""])
    mp = report["milestone_progress"]
    for key in ("total", "completed", "in_progress", "pending", "cancelled"):
        writer.writerow([f"milestones_{key}", mp[key]])
    ba = report["blocker_analysis"]
    writer.writerow(["blocked_total", ba["blocked_total"]])
    return buffer.getvalue(), len(report["series"])
