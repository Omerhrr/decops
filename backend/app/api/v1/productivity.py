"""Productivity endpoints: saved filters, bulk task actions, global search.

Authorization is never re-implemented here: bulk actions call the same
service functions as the single-task endpoints (each task is authorized on
its own, so one forbidden/missing task cannot affect or reveal the others),
and search goes through the authorization-aware task listing.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import DbSession, CurrentUser
from app.core.context import current_request_id
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.domain.access_policy import Operation
from app.domain.task_lifecycle import TransitionError
from app.models import SavedFilter, TaskPriority, User
from app.services import audit_service, task_service

router = APIRouter(tags=["Productivity"])

MAX_SAVED_FILTERS = 25
MAX_BULK = 100
ALLOWED_FILTER_KEYS = {"status", "priority", "q", "department_id", "accountable_pm_id"}


def _auth(request: Request, user: CurrentUser) -> User:
    request.state.user = user
    return user


# ---------------------------------------------------------------- saved filters

class SavedFilterIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    params: dict[str, str] = Field(default_factory=dict)


def _filter_out(f: SavedFilter) -> dict:
    return {"id": str(f.id), "name": f.name, "params": f.params or {}}


@router.get("/saved-filters")
def list_saved_filters(db: DbSession, user: User = Depends(_auth)) -> list[dict]:
    rows = db.scalars(
        select(SavedFilter).where(SavedFilter.user_id == user.id).order_by(SavedFilter.name)
    ).all()
    return [_filter_out(r) for r in rows]


@router.post("/saved-filters", status_code=201)
def create_saved_filter(payload: SavedFilterIn, db: DbSession, user: User = Depends(_auth)) -> dict:
    name = payload.name.strip()
    if not name:
        raise ValidationFailedError("Filter name must not be empty.")
    params = {k: v[:200] for k, v in payload.params.items() if k in ALLOWED_FILTER_KEYS and v}
    count = db.scalar(select(func.count(SavedFilter.id)).where(SavedFilter.user_id == user.id)) or 0
    existing = db.scalar(
        select(SavedFilter).where(SavedFilter.user_id == user.id, SavedFilter.name == name)
    )
    if existing is not None:  # same name replaces the stored params
        existing.params = params
        db.commit()
        return _filter_out(existing)
    if count >= MAX_SAVED_FILTERS:
        raise ConflictError(f"You can save up to {MAX_SAVED_FILTERS} filters.", code="saved_filter_limit")
    row = SavedFilter(user_id=user.id, name=name, params=params)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _filter_out(row)


@router.delete("/saved-filters/{filter_id}", status_code=204)
def delete_saved_filter(filter_id: uuid.UUID, db: DbSession, user: User = Depends(_auth)) -> None:
    row = db.get(SavedFilter, filter_id)
    if row is None or row.user_id != user.id:
        raise NotFoundError("Saved filter not found.")
    db.delete(row)
    db.commit()


# ------------------------------------------------------------------ bulk actions

class BulkRequest(BaseModel):
    task_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_BULK)
    action: Literal["transition", "set_priority"]
    to_status: str | None = None
    priority: str | None = None
    reason: str | None = Field(default=None, max_length=2000)


@router.post("/tasks/bulk")
def bulk_tasks(payload: BulkRequest, db: DbSession, user: User = Depends(_auth)) -> dict:
    if payload.action == "transition" and not payload.to_status:
        raise ValidationFailedError("to_status is required for a transition.")
    if payload.action == "set_priority":
        try:
            priority = TaskPriority(payload.priority or "")
        except ValueError as exc:
            raise ValidationFailedError("A valid priority is required.") from exc

    results: list[dict] = []
    for task_id in dict.fromkeys(payload.task_ids):
        savepoint = db.begin_nested()
        try:
            if payload.action == "transition":
                task = task_service.get_task_for_actor(db, user, task_id)
                task_service.transition_task(
                    db, actor=user, task=task, to_status=payload.to_status,
                    reason=payload.reason, request_id=current_request_id(),
                )
            else:
                task = task_service.get_task_for_actor(db, user, task_id, operation=Operation.UPDATE)
                task_service.update_task(
                    db, actor=user, task=task, expected_version=task.version,
                    fields={"priority": priority}, request_id=current_request_id(),
                )
            savepoint.commit()
            results.append({"task_id": str(task_id), "ok": True})
        except NotFoundError:
            savepoint.rollback()  # same wording for "missing" and "not allowed"
            results.append({"task_id": str(task_id), "ok": False, "error": "Task not found."})
        except (task_service.TaskError, TransitionError, ValidationFailedError) as exc:
            savepoint.rollback()
            results.append({"task_id": str(task_id), "ok": False, "error": str(getattr(exc, "message", exc))})
    succeeded = sum(1 for r in results if r["ok"])
    audit_service.record_audit_event(
        db, action="task.bulk", resource_type="task", actor=user,
        request_id=current_request_id(),
        change_summary=f"Bulk {payload.action}: {succeeded}/{len(results)} succeeded",
        metadata={"action": payload.action, "requested": len(results), "succeeded": succeeded},
    )
    db.commit()
    return {"results": results, "succeeded": succeeded, "failed": len(results) - succeeded}


# ------------------------------------------------------------------------ search

@router.get("/search")
def global_search(
    db: DbSession, user: User = Depends(_auth),
    q: str = Query(min_length=2, max_length=100),
) -> dict:
    tasks, _ = task_service.list_tasks_for_actor(db, user, q=q, page=1, page_size=8)
    return {
        "tasks": [
            {
                "id": str(t.id), "task_number": t.task_number, "title": t.title,
                "status": str(getattr(t.status, "value", t.status)),
            }
            for t in tasks
        ],
    }
