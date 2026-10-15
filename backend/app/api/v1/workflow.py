"""Workflow engine endpoints (MOD-004, Phase 5).

All workflow operations are nested under /tasks/{task_id}/... and guarded by
the task access-policy engine inside the service (404 for unauthorized
actors). Template administration is gated by the global tasks.manage_all
permission at the route level.
"""

import uuid

from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import CurrentUser, DbSession, require_permission
from app.core.errors import ConflictError, ValidationFailedError
from app.domain.workflow import WorkflowTransitionError
from app.schemas.workflow import (
    DependencyCreateRequest,
    DependencyOut,
    ProgressModeRequest,
    StageCreateRequest,
    StageOut,
    StageProgressOut,
    StageTransitionRequest,
    StageUpdateRequest,
    WorkItemAssignRequest,
    WorkItemCreateRequest,
    WorkItemOut,
    WorkItemTransitionRequest,
    WorkItemUpdateRequest,
    WorkflowOut,
    WorkflowProgressOut,
    WorkflowTemplateCreateRequest,
    WorkflowTemplateOut,
    WorkflowTemplateUpdateRequest,
    WorkflowTemplatesOut,
)
from app.services import workflow_service

router = APIRouter(tags=["Workflow"])


def _auth(request: Request, user: CurrentUser):
    request.state.user = user
    return user


@router.get("/tasks/{task_id}/workflow")
def get_workflow(
    task_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> WorkflowOut:
    _auth(request, user)
    task, stages, items, edges, blockers, actionable, progress = (
        workflow_service.get_workflow(db, user, task_id)
    )
    return WorkflowOut(
        task_id=task.id,
        task_status=str(getattr(task.status, "value", task.status)),
        task_progress_mode=str(getattr(task.progress_mode, "value", task.progress_mode)),
        task_percent_complete=task.percent_complete,
        calculated_percent=progress.task_percent,
        stages=[
            StageOut(
                id=s.id, task_id=s.task_id, name=s.name, description=s.description,
                sequence_number=s.sequence_number,
                execution_mode=str(getattr(s.execution_mode, "value", s.execution_mode)),
                status=str(getattr(s.status, "value", s.status)),
                weight=s.weight,
                progress_basis=str(getattr(s.progress_basis, "value", s.progress_basis)),
                start_date=s.start_date, due_date=s.due_date,
                completed_at=s.completed_at,
            )
            for s in stages
        ],
        items=[WorkItemOut.model_validate(i) for i in items],
        dependencies=[DependencyOut.model_validate(d) for d in _dependency_rows(db, task.id, edges)],
        blockers=[
            {"item_id": str(item_id), "blocked_by": [str(p) for p in preds]}
            for item_id, preds in blockers.items()
        ],
        actionable_stage_ids=actionable,
        progress=WorkflowProgressOut(
            task_percent=progress.task_percent,
            counted_item_total=progress.counted_item_total,
            counted_item_completed=progress.counted_item_completed,
            method=progress.method,
            stages=[
                StageProgressOut(
                    stage_id=b.stage_id, stage_name=b.stage_name, status=b.status,
                    weight=b.weight, included_item_count=b.included_item_count,
                    completed_item_count=b.completed_item_count,
                    total_weight=b.total_weight, completed_weight=b.completed_weight,
                    percent=b.percent, excluded=b.excluded, method=b.method,
                )
                for b in progress.stages
            ],
        ),
    )


def _dependency_rows(db, task_id, edges):
    from app.models import WorkItemDependency
    from sqlalchemy import select
    return list(db.scalars(select(WorkItemDependency).where(WorkItemDependency.task_id == task_id)))


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------

@router.post("/tasks/{task_id}/stages", status_code=201)
def create_stage(
    task_id: uuid.UUID,
    payload: StageCreateRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> StageOut:
    _auth(request, user)
    stage = workflow_service.create_stage(db, user, task_id, payload)
    db.commit()
    return _stage_out(stage)


@router.patch("/tasks/{task_id}/stages/{stage_id}")
def update_stage(
    task_id: uuid.UUID,
    stage_id: uuid.UUID,
    payload: StageUpdateRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> StageOut:
    _auth(request, user)
    stage = workflow_service.update_stage(db, user, task_id, stage_id, payload)
    db.commit()
    return _stage_out(stage)


@router.post("/tasks/{task_id}/stages/{stage_id}/transition")
def transition_stage(
    task_id: uuid.UUID,
    stage_id: uuid.UUID,
    payload: StageTransitionRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> StageOut:
    _auth(request, user)
    stage = workflow_service.transition_stage(
        db, user, task_id, stage_id, payload.to_status, payload.reason
    )
    db.commit()
    return _stage_out(stage)


@router.delete("/tasks/{task_id}/stages/{stage_id}", status_code=204)
def delete_stage(
    task_id: uuid.UUID,
    stage_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> Response:
    _auth(request, user)
    workflow_service.delete_stage(db, user, task_id, stage_id)
    db.commit()
    return Response(status_code=204)


def _stage_out(stage) -> StageOut:
    return StageOut(
        id=stage.id, task_id=stage.task_id, name=stage.name,
        description=stage.description, sequence_number=stage.sequence_number,
        execution_mode=str(getattr(stage.execution_mode, "value", stage.execution_mode)),
        status=str(getattr(stage.status, "value", stage.status)),
        weight=stage.weight,
        progress_basis=str(getattr(stage.progress_basis, "value", stage.progress_basis)),
        start_date=stage.start_date, due_date=stage.due_date,
        completed_at=stage.completed_at,
    )


# ---------------------------------------------------------------------------
# Work items
# ---------------------------------------------------------------------------

@router.post("/tasks/{task_id}/stages/{stage_id}/items", status_code=201)
def create_item(
    task_id: uuid.UUID,
    stage_id: uuid.UUID,
    payload: WorkItemCreateRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> WorkItemOut:
    _auth(request, user)
    item = workflow_service.create_item(db, user, task_id, stage_id, payload)
    db.commit()
    return WorkItemOut.model_validate(item)


@router.patch("/tasks/{task_id}/items/{item_id}")
def update_item(
    task_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: WorkItemUpdateRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> WorkItemOut:
    _auth(request, user)
    item = workflow_service.update_item(db, user, task_id, item_id, payload)
    db.commit()
    return WorkItemOut.model_validate(item)


@router.post("/tasks/{task_id}/items/{item_id}/transition")
def transition_item(
    task_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: WorkItemTransitionRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> WorkItemOut:
    _auth(request, user)
    item = workflow_service.transition_item(
        db, user, task_id, item_id, payload.to_status, payload.reason
    )
    db.commit()
    return WorkItemOut.model_validate(item)


@router.post("/tasks/{task_id}/items/{item_id}/assign")
def assign_item(
    task_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: WorkItemAssignRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> WorkItemOut:
    _auth(request, user)
    item = workflow_service.assign_item(db, user, task_id, item_id, payload.assigned_user_id)
    db.commit()
    return WorkItemOut.model_validate(item)


@router.delete("/tasks/{task_id}/items/{item_id}", status_code=204)
def delete_item(
    task_id: uuid.UUID,
    item_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> Response:
    _auth(request, user)
    workflow_service.delete_item(db, user, task_id, item_id)
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

@router.post("/tasks/{task_id}/dependencies", status_code=201)
def add_dependency(
    task_id: uuid.UUID,
    payload: DependencyCreateRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> DependencyOut:
    _auth(request, user)
    dependency = workflow_service.add_dependency(db, user, task_id, payload)
    db.commit()
    return DependencyOut.model_validate(dependency)


@router.delete("/tasks/{task_id}/dependencies/{dependency_id}", status_code=204)
def remove_dependency(
    task_id: uuid.UUID,
    dependency_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> Response:
    _auth(request, user)
    workflow_service.remove_dependency(db, user, task_id, dependency_id)
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Progress mode (AC-06)
# ---------------------------------------------------------------------------

@router.post("/tasks/{task_id}/workflow-settings")
def set_progress_mode(
    task_id: uuid.UUID,
    payload: ProgressModeRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
):
    _auth(request, user)
    task = workflow_service.set_progress_mode(
        db, user, task_id, payload.progress_mode, payload.reason
    )
    db.commit()
    progress, _, _ = workflow_service.calculate_progress(db, task)
    return {
        "task_id": str(task.id),
        "progress_mode": str(getattr(task.progress_mode, "value", task.progress_mode)),
        "percent_complete": task.percent_complete,
        "calculated_percent": progress.task_percent,
        "method": progress.method,
    }


# ---------------------------------------------------------------------------
# Workflow templates (Administration; global permission gate)
# ---------------------------------------------------------------------------

templates_router = APIRouter(
    prefix="/workflow-templates",
    tags=["Workflow Templates"],
    dependencies=[Depends(require_permission("tasks.manage_all"))],
)


@templates_router.get("")
def list_templates(user: CurrentUser, db: DbSession) -> WorkflowTemplatesOut:
    rows = workflow_service.list_templates(db)
    return WorkflowTemplatesOut(
        items=[WorkflowTemplateOut.model_validate(t) for t in rows], total=len(rows)
    )


@templates_router.post("", status_code=201)
def create_template(
    payload: WorkflowTemplateCreateRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> WorkflowTemplateOut:
    _auth(request, user)
    template = workflow_service.create_template(db, user, payload)
    db.commit()
    return WorkflowTemplateOut.model_validate(template)


@templates_router.patch("/{template_id}")
def update_template(
    template_id: uuid.UUID,
    payload: WorkflowTemplateUpdateRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> WorkflowTemplateOut:
    _auth(request, user)
    template = workflow_service.update_template(db, user, template_id, payload)
    db.commit()
    return WorkflowTemplateOut.model_validate(template)
