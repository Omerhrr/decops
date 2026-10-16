"""Task management endpoints.

Route-level: global permission gates for task creation only. Every other
operation is guarded by the task access-policy engine inside the service -
a user who merely knows a task id gets 404, never 403.
"""

import uuid

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import CurrentUser, DbSession, require_permission
from app.core.context import current_request_id
from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError, ValidationFailedError
from app.domain import assignment_policy
from app.domain.access_policy import Operation
from app.domain.task_lifecycle import ALLOWED_TRANSITIONS, TaskStatus
from app.models import AccessLevel, AssignmentRoleType, ParticipationType, ProgressMode, TaskPriority, User
from app.schemas.tasks import (
    TaskAccessGrantOut,
    TaskAccessGrantRequest,
    TaskActivityOut,
    TaskAssignRequest,
    TaskCreateRequest,
    TaskDepartmentAddRequest,
    TaskDepartmentOut,
    TaskDetailOut,
    TaskOut,
    TaskPage,
    TaskTransitionRequest,
    TaskUpdateRequest,
    TaskUserBrief,
    TransitionOptionsOut,
)
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["Tasks"])


def _auth(request: Request, user: CurrentUser) -> User:
    request.state.user = user
    return user


def _out(task) -> dict:
    return TaskOut(
        id=task.id,
        task_number=task.task_number,
        title=task.title,
        priority=task.priority,
        status=str(getattr(task.status, "value", task.status)),
        accountable_pm_id=task.accountable_pm_id,
        accountable_pm=TaskUserBrief.model_validate(task.accountable_pm) if task.accountable_pm else None,
        start_date=task.start_date,
        due_date=task.due_date,
        next_follow_up_date=task.next_follow_up_date,
        percent_complete=task.percent_complete,
        progress_mode=task.progress_mode,
        visibility_mode=task.visibility_mode,
        created_at=task.created_at,
        department_names=[td.department.name for td in task.task_departments if td.department],
    ).model_dump(mode="json")


def _detail_out(task) -> dict:
    return TaskDetailOut(
        **_out(task),
        description=task.description,
        created_by_id=task.created_by_id,
        dependency_summary=task.dependency_summary,
        legacy_external_id=task.legacy_external_id,
        attachment_folder_reference=task.attachment_folder_reference,
        version=task.version,
        completed_at=task.completed_at,
        cancelled_at=task.cancelled_at,
        archived_at=task.archived_at,
        updated_at=task.updated_at,
        assignments=task.assignments,
        task_departments=[
            TaskDepartmentOut(
                id=td.id, department_id=td.department_id,
                department_name=td.department.name if td.department else None,
                participation_type=td.participation_type,
            )
            for td in task.task_departments
        ],
        access_grants=[TaskAccessGrantOut.model_validate(g) for g in task.access_grants],
    ).model_dump(mode="json")


@router.get("")
def list_tasks(
    db: DbSession,
    user: User = Depends(_auth),
    status: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    department_id: uuid.UUID | None = Query(default=None),
    accountable_pm_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> dict:
    tasks, total = task_service.list_tasks_for_actor(
        db, user, status=status, priority=priority, q=q,
        department_id=department_id, accountable_pm_id=accountable_pm_id,
        page=page, page_size=page_size,
    )
    return TaskPage(
        items=[TaskOut(**_out(t)) for t in tasks],
        total=total, page=page, page_size=page_size,
    ).model_dump(mode="json")


@router.post("", status_code=201,
             dependencies=[Depends(require_permission("tasks.create"))])
def create_task(payload: TaskCreateRequest, request: Request, db: DbSession) -> dict:
    actor: User = request.state.user
    try:
        task = task_service.create_task(
            db, actor=actor, title=payload.title, accountable_pm_id=payload.accountable_pm_id,
            priority=payload.priority, description=payload.description,
            start_date=payload.start_date, due_date=payload.due_date,
            next_follow_up_date=payload.next_follow_up_date,
            dependency_summary=payload.dependency_summary,
            visibility_mode=payload.visibility_mode, progress_mode=payload.progress_mode,
            department_ids=payload.department_ids, participation_type=payload.participation_type,
            grant_user_ids=payload.grant_user_ids, grant_access_level=payload.grant_access_level,
            request_id=current_request_id(),
        )
    except task_service.TaskError as exc:
        raise ConflictError(exc.message, code=exc.code) from exc
    db.commit()
    db.refresh(task)
    return _detail_out(task)


@router.get("/{task_id}")
def get_task(task_id: uuid.UUID, request: Request, db: DbSession, user: User = Depends(_auth)) -> dict:
    task = task_service.get_task_for_actor(db, user, task_id)
    return _detail_out(task)


@router.patch("/{task_id}")
def update_task(
    task_id: uuid.UUID, payload: TaskUpdateRequest, request: Request, db: DbSession,
    user: User = Depends(_auth),
) -> dict:
    # UPDATE (not VIEW) is the operation that guards a mutation; a user who may
    # only view the task gets the same 404 as the rest of the world.
    task = task_service.get_task_for_actor(db, user, task_id, operation=Operation.UPDATE)
    fields = {k: getattr(payload, k) for k in payload.model_fields_set}
    try:
        task = task_service.update_task(
            db, actor=user, task=task, expected_version=payload.version,
            fields=fields, request_id=current_request_id(),
        )
    except task_service.TaskError as exc:
        raise ConflictError(exc.message, code=exc.code) from exc
    db.commit()
    db.refresh(task)
    return _detail_out(task)


@router.post("/{task_id}/transition")
def transition_task(
    task_id: uuid.UUID, payload: TaskTransitionRequest, request: Request, db: DbSession,
    user: User = Depends(_auth),
) -> dict:
    task = task_service.get_task_for_actor(db, user, task_id)
    try:
        task = task_service.transition_task(
            db, actor=user, task=task, to_status=payload.to_status,
            reason=payload.reason, request_id=current_request_id(),
        )
    except Exception as exc:
        from app.domain.task_lifecycle import TransitionError

        if isinstance(exc, task_service.TaskError):
            raise ConflictError(exc.message, code=exc.code) from exc
        if isinstance(exc, TransitionError):
            raise ValidationFailedError(str(exc), code=exc.code) from exc
        raise
    db.commit()
    db.refresh(task)
    return _detail_out(task)


@router.get("/{task_id}/transition-options")
def transition_options(
    task_id: uuid.UUID, request: Request, db: DbSession, user: User = Depends(_auth)
) -> dict:
    task = task_service.get_task_for_actor(db, user, task_id)
    current = TaskStatus(str(getattr(task.status, "value", task.status)))
    return TransitionOptionsOut(
        current_status=current.value,
        allowed_transitions=sorted(t.value for t in ALLOWED_TRANSITIONS.get(current, frozenset())),
    ).model_dump(mode="json")


@router.post("/{task_id}/assignments", status_code=201)
def assign_user(
    task_id: uuid.UUID, payload: TaskAssignRequest, request: Request, db: DbSession,
    user: User = Depends(_auth),
) -> dict:
    task = task_service.get_task_for_actor(db, user, task_id)
    try:
        task_service.assign_user(
            db, actor=user, task=task, user_id=payload.user_id,
            role=payload.assignment_role, request_id=current_request_id(),
        )
    except assignment_policy.AssignmentDeniedError as exc:
        if "permission to assign" in exc.reason:
            raise PermissionDeniedError() from exc
        raise ValidationFailedError(exc.reason) from exc
    db.commit()
    db.refresh(task)
    return _detail_out(task)


@router.delete("/{task_id}/assignments/{assignment_id}", status_code=204)
def revoke_assignment(
    task_id: uuid.UUID, assignment_id: uuid.UUID, request: Request, db: DbSession,
    user: User = Depends(_auth),
) -> None:
    task = task_service.get_task_for_actor(db, user, task_id)
    task_service.revoke_assignment(
        db, actor=user, task=task, assignment_id=assignment_id,
        request_id=current_request_id(),
    )
    db.commit()


@router.post("/{task_id}/departments", status_code=201)
def add_department(
    task_id: uuid.UUID, payload: TaskDepartmentAddRequest, request: Request, db: DbSession,
    user: User = Depends(_auth),
) -> dict:
    task = task_service.get_task_for_actor(db, user, task_id)
    try:
        task_service.add_department(
            db, actor=user, task=task, department_id=payload.department_id,
            participation_type=payload.participation_type, request_id=current_request_id(),
        )
    except task_service.TaskError as exc:
        raise ConflictError(exc.message, code=exc.code) from exc
    db.commit()
    db.refresh(task)
    return _detail_out(task)


@router.post("/{task_id}/access-grants", status_code=201)
def add_access_grant(
    task_id: uuid.UUID, payload: TaskAccessGrantRequest, request: Request, db: DbSession,
    user: User = Depends(_auth),
) -> dict:
    task = task_service.get_task_for_actor(db, user, task_id)
    try:
        task_service.add_access_grant(
            db, actor=user, task=task, user_id=payload.user_id,
            access_level=payload.access_level, request_id=current_request_id(),
        )
    except task_service.TaskError as exc:
        raise ConflictError(exc.message, code=exc.code) from exc
    db.commit()
    db.refresh(task)
    return _detail_out(task)


@router.delete("/{task_id}/access-grants/{grant_id}", status_code=204)
def revoke_access_grant(
    task_id: uuid.UUID, grant_id: uuid.UUID, request: Request, db: DbSession,
    user: User = Depends(_auth),
) -> None:
    task = task_service.get_task_for_actor(db, user, task_id)
    task_service.revoke_access_grant(
        db, actor=user, task=task, grant_id=grant_id, request_id=current_request_id(),
    )
    db.commit()


@router.get("/{task_id}/activity")
def list_activity(
    task_id: uuid.UUID, request: Request, db: DbSession, user: User = Depends(_auth)
) -> list[dict]:
    task = task_service.get_task_for_actor(db, user, task_id)
    return [
        TaskActivityOut.model_validate(a).model_dump(mode="json")
        for a in task_service.list_activity(db, task)
    ]
