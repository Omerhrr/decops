"""Recurring tasks: spawn ordinary tasks on a schedule (run by the worker)."""

import calendar
import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_user_permission_codes
from app.models import RecurringTask, TaskPriority, User
from app.services import task_service

logger = logging.getLogger("decops.recurrence")
FREQUENCIES = ("daily", "weekly", "monthly")


def advance(day: date, frequency: str, interval: int) -> date:
    if frequency == "daily":
        return day + timedelta(days=interval)
    if frequency == "weekly":
        return day + timedelta(weeks=interval)
    month_index = day.month - 1 + interval
    year, month = day.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def run_due(db: Session, *, today: date | None = None) -> dict:
    """Create one task per due template (no backfill of missed periods)."""
    today = today or datetime.now(UTC).date()
    templates = db.scalars(
        select(RecurringTask).where(RecurringTask.active.is_(True), RecurringTask.next_run_on <= today)
    ).all()
    created = failed = 0
    for tpl in templates:
        savepoint = db.begin_nested()
        try:
            actor = db.get(User, tpl.created_by_id)
            if actor is None or str(getattr(actor.account_status, "value", actor.account_status)) != "active":
                raise ValueError("The template owner's account is not active.")
            if "tasks.create" not in get_user_permission_codes(db, actor):
                raise ValueError("The template owner can no longer create tasks.")
            task_service.create_task(
                db, actor=actor, title=tpl.title, accountable_pm_id=tpl.accountable_pm_id,
                priority=TaskPriority(tpl.priority), description=tpl.description,
                start_date=today, due_date=today + timedelta(days=tpl.due_after_days),
                visibility_mode=tpl.visibility_mode,
                department_ids=[uuid.UUID(d) for d in (tpl.department_ids or [])],
            )
            savepoint.commit()
            tpl.last_error = None
            created += 1
        except Exception as exc:  # noqa: BLE001 - record and keep the schedule moving
            savepoint.rollback()
            tpl.last_error = str(getattr(exc, "message", exc))[:300]
            failed += 1
        tpl.last_run_at = datetime.now(UTC)
        nxt = advance(tpl.next_run_on, tpl.frequency, tpl.interval)
        while nxt <= today:  # skip missed periods instead of flooding
            nxt = advance(nxt, tpl.frequency, tpl.interval)
        tpl.next_run_on = nxt
    if templates:
        db.commit()
    return {"created": created, "failed": failed}
