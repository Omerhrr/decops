"""Workflow engine service (MOD-004, Phase 5).

Every mutation is authorized through the task access-policy engine (fresh
actor state per request), validated by the pure domain rules in
app.domain.workflow, audited (audit_events) AND recorded on the task's
activity timeline. Authorization failures surface as 404 (non-enumeration).

Authorization mapping (access_policy.Operation):
- reads                        -> VIEW
- structure/dependencies/assign/progress-mode -> MANAGE_WORKFLOW
- work item start/complete/reopen -> COMPLETE
- work item cancel             -> CANCEL
- stage transitions            -> MANAGE_WORKFLOW
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, joinedload

from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.domain import access_policy, workflow as wf
from app.domain.access_policy import Operation
from app.domain.progress import StageFacts, compute_progress, milestone_effectively_complete
from app.domain.task_lifecycle import TaskStatus
from app.domain.workflow import ItemFacts
from app.models import (
    ProgressBasis,
    StageExecutionMode,
    StageStatus,
    Task,
    TaskStage,
    User,
    WorkItem,
    WorkItemDependency,
    WorkItemStatus,
    WorkItemType,
    WorkflowTemplate,
)
from app.services import audit_service, task_service

_EXECUTABLE_TASK_STATUSES = {"in_progress"}
_EDITABLE_TASK_STATUSES = {"draft", "open", "in_progress", "blocked"}


def _enum_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _ensure_task_editable(task: Task) -> None:
    status = _enum_value(task.status)
    if status not in _EDITABLE_TASK_STATUSES:
        raise ConflictError(
            f"The workflow of a '{status}' task cannot be modified.",
            code="task_not_editable",
        )


def _ensure_task_executing(task: Task) -> None:
    status = _enum_value(task.status)
    if status not in _EXECUTABLE_TASK_STATUSES:
        raise ValidationFailedError(
            "Workflow work can only start or complete while the task is in progress.",
            code="task_not_in_progress",
        )


def _load_stage(db: Session, task_id: uuid.UUID, stage_id: uuid.UUID) -> TaskStage:
    stage = db.scalar(
        select(TaskStage).where(TaskStage.id == stage_id, TaskStage.task_id == task_id)
    )
    if stage is None:
        raise NotFoundError("Workflow stage not found.")
    return stage


def _load_item(db: Session, task_id: uuid.UUID, item_id: uuid.UUID) -> WorkItem:
    item = db.scalar(
        select(WorkItem).where(WorkItem.id == item_id, WorkItem.task_id == task_id)
    )
    if item is None:
        raise NotFoundError("Work item not found.")
    return item


# ---------------------------------------------------------------------------
# Graph helpers
# ---------------------------------------------------------------------------

def load_edges(db: Session, task_id: uuid.UUID) -> set[wf.Edge]:
    rows = db.execute(
        select(WorkItemDependency.predecessor_id, WorkItemDependency.successor_id)
        .where(WorkItemDependency.task_id == task_id)
    ).all()
    return {wf.Edge(predecessor_id=p, successor_id=s) for p, s in rows}


def _task_items(db: Session, task: Task) -> list[WorkItem]:
    return list(
        db.scalars(
            select(WorkItem)
            .options(joinedload(WorkItem.assignee))
            .where(WorkItem.task_id == task.id)
            .order_by(WorkItem.stage_id, WorkItem.sequence_number)
        )
    )


def _task_stages(db: Session, task: Task) -> list[TaskStage]:
    return list(
        db.scalars(
            select(TaskStage)
            .where(TaskStage.task_id == task.id)
            .order_by(TaskStage.sequence_number)
        )
    )


def _item_facts(items: list[WorkItem]) -> list[ItemFacts]:
    return [
        ItemFacts(
            id=i.id,
            item_type=_enum_value(i.item_type),
            parent_id=i.parent_work_item_id,
            status=_enum_value(i.status),
            is_required=i.is_required,
            weight=i.weight,
            title=i.title,
        )
        for i in items
    ]


def _progress_facts(
    stages: list[TaskStage], items: list[WorkItem]
) -> tuple[list[StageFacts], list[ItemFacts]]:
    stage_facts = [
        StageFacts(
            id=str(s.id),
            name=s.name,
            sequence_number=s.sequence_number,
            status=_enum_value(s.status),
            weight=s.weight,
            progress_basis=_enum_value(s.progress_basis),
            item_ids=frozenset(str(i.id) for i in items if i.stage_id == s.id),
        )
        for s in stages
    ]
    return stage_facts, _item_facts(items)


def calculate_progress(db: Session, task: Task) -> tuple:
    stages = _task_stages(db, task)
    items = _task_items(db, task)
    stage_facts, item_facts = _progress_facts(stages, items)
    return compute_progress(stage_facts, item_facts), stages, items


def sync_task_percent(db: Session, task: Task) -> int:
    """Write engine progress into tasks.percent_complete when the task is in
    calculated mode (AC-06: manual and calculated stay distinguishable)."""
    if _enum_value(task.progress_mode) != "calculated":
        return int(task.percent_complete or 0)
    progress, _, _ = calculate_progress(db, task)
    task.percent_complete = progress.task_percent
    return progress.task_percent


# ---------------------------------------------------------------------------
# Audit + activity
# ---------------------------------------------------------------------------

def _audit(db, *, actor: User, task: Task, action: str, resource_type: str,
           resource_id, summary: str, reason: str | None = None,
           metadata: dict | None = None) -> None:
    audit_service.record_audit_event(
        db,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        actor=actor,
        reason=reason,
        change_summary=summary[:500],
        metadata={"task_id": str(task.id), **(metadata or {})},
    )
    task_service.record_activity(
        db, task=task, actor=actor, activity_type=action,
        summary=summary, detail={"reason": reason} if reason else None,
    )


# ---------------------------------------------------------------------------
# Sequence management (insert/remove without violating uniqueness)
# ---------------------------------------------------------------------------

def _shift_sequences(db: Session, model, scope_filter, from_seq: int,
                     direction: int, *, exclude_id=None) -> None:
    """Shift sequence numbers by `direction` for rows at/after `from_seq`,
    ordered so the unique constraint is never transiently violated.
    Core-level updates with synchronize_session=False keep the unit of work
    from re-emitting stale ORM updates."""
    column = model.sequence_number
    query = select(model).where(scope_filter, column >= from_seq)
    if exclude_id is not None:
        query = query.where(model.id != exclude_id)
    order = column.desc() if direction > 0 else column.asc()
    rows = db.execute(
        select(model.id, column).where(
            scope_filter, column >= from_seq,
            *([model.id != exclude_id] if exclude_id is not None else []),
        ).order_by(order)
    ).all()
    for row_id, seq in rows:
        db.execute(
            update(model)
            .where(model.id == row_id)
            .values(sequence_number=seq + direction)
            .execution_options(synchronize_session=False)
        )
    db.flush()


def _next_sequence(db: Session, model, scope_filter) -> int:
    current_max = db.scalar(select(func.max(model.sequence_number)).where(scope_filter))
    return (current_max or 0) + 1


def _move_within_scope(db: Session, model, scope_filter, row, old: int, new: int) -> None:
    """Reposition a sequenced row from `old` to `new` without ever violating
    the unique (scope, sequence_number) constraint: lift the row to a
    temporary free slot beyond the current maximum, close the gap, then
    drop it into the target position."""
    temp = _next_sequence(db, model, scope_filter)
    db.execute(
        update(model).where(model.id == row.id)
        .values(sequence_number=temp)
        .execution_options(synchronize_session=False)
    )
    db.flush()
    if new > old:
        # Rows strictly between old and new close down by one (ascending).
        rows = db.execute(
            select(model.id, model.sequence_number).where(
                scope_filter, model.sequence_number > old, model.sequence_number <= new,
            ).order_by(model.sequence_number.asc())
        ).all()
        for row_id, seq in rows:
            db.execute(
                update(model).where(model.id == row_id)
                .values(sequence_number=seq - 1)
                .execution_options(synchronize_session=False)
            )
    else:
        # Rows between new and old open up by one (descending).
        rows = db.execute(
            select(model.id, model.sequence_number).where(
                scope_filter, model.sequence_number >= new, model.sequence_number < old,
            ).order_by(model.sequence_number.desc())
        ).all()
        for row_id, seq in rows:
            db.execute(
                update(model).where(model.id == row_id)
                .values(sequence_number=seq + 1)
                .execution_options(synchronize_session=False)
            )
    db.flush()
    row.sequence_number = new
    db.flush()


def _move_stage(db: Session, task_id: uuid.UUID, stage: TaskStage,
                old: int, new: int) -> None:
    _move_within_scope(db, TaskStage, TaskStage.task_id == task_id, stage, old, new)


def _move_item(db: Session, item: WorkItem, old: int, new: int) -> None:
    _move_within_scope(db, WorkItem, WorkItem.stage_id == item.stage_id, item, old, new)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def get_workflow(db: Session, actor: User, task_id: uuid.UUID):
    task = task_service.get_task_for_actor(db, actor, task_id, Operation.VIEW)
    stages = _task_stages(db, task)
    items = _task_items(db, task)
    edges = load_edges(db, task.id)

    item_status = {i.id: _enum_value(i.status) for i in items}
    blockers = wf.blockers_for(edges, item_status)

    pending_stage_states = [
        wf.StageState(
            id=s.id,
            sequence_number=s.sequence_number,
            execution_mode=_enum_value(s.execution_mode),
            status=_enum_value(s.status),
        )
        for s in stages
    ]
    actionable = [
        str(s.id)
        for s in stages
        if _enum_value(s.status) == "pending" and wf.stage_is_actionable(pending_stage_states, s.id)
    ]

    stage_facts, item_facts = _progress_facts(stages, items)
    progress = compute_progress(stage_facts, item_facts)

    return task, stages, items, edges, blockers, actionable, progress


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------

def create_stage(db: Session, actor: User, task_id: uuid.UUID, data) -> TaskStage:
    task = task_service.get_task_for_actor(db, actor, task_id, Operation.MANAGE_WORKFLOW)
    _ensure_task_editable(task)

    if data.sequence_number is not None:
        _shift_sequences(
            db, TaskStage, TaskStage.task_id == task.id, data.sequence_number, +1
        )
        sequence = data.sequence_number
    else:
        sequence = _next_sequence(db, TaskStage, TaskStage.task_id == task.id)

    stage = TaskStage(
        task_id=task.id,
        name=data.name.strip(),
        description=data.description,
        sequence_number=sequence,
        execution_mode=StageExecutionMode(data.execution_mode.value),
        status=StageStatus.pending,
        weight=data.weight,
        progress_basis=ProgressBasis(data.progress_basis.value),
        start_date=data.start_date,
        due_date=data.due_date,
    )
    db.add(stage)
    db.flush()
    _audit(
        db, actor=actor, task=task, action="workflow.stage_created",
        resource_type="task_stage", resource_id=stage.id,
        summary=f"Added stage {sequence} \"{stage.name}\" "
                f"({_enum_value(stage.execution_mode)}) to the workflow.",
    )
    sync_task_percent(db, task)
    return stage


def update_stage(db: Session, actor: User, task_id: uuid.UUID,
                 stage_id: uuid.UUID, data) -> TaskStage:
    task = task_service.get_task_for_actor(db, actor, task_id, Operation.MANAGE_WORKFLOW)
    _ensure_task_editable(task)
    stage = _load_stage(db, task.id, stage_id)

    changes: list[str] = []
    if data.name is not None and data.name.strip() != stage.name:
        changes.append(f"renamed to \"{data.name.strip()}\"")
        stage.name = data.name.strip()
    if data.description is not None:
        stage.description = data.description
    if data.execution_mode is not None and _enum_value(stage.execution_mode) != data.execution_mode.value:
        stage.execution_mode = StageExecutionMode(data.execution_mode.value)
        changes.append(f"execution mode set to {data.execution_mode.value}")
    if data.weight is not None and data.weight != stage.weight:
        stage.weight = data.weight
        changes.append(f"weight set to {data.weight}")
    if data.progress_basis is not None and _enum_value(stage.progress_basis) != data.progress_basis.value:
        stage.progress_basis = ProgressBasis(data.progress_basis.value)
        changes.append(f"progress basis set to {data.progress_basis.value}")
    if data.start_date is not None:
        stage.start_date = data.start_date
    if data.due_date is not None:
        stage.due_date = data.due_date
    if stage.start_date and stage.due_date and stage.due_date < stage.start_date:
        raise ValidationFailedError("due_date cannot be before start_date.")

    if data.sequence_number is not None and data.sequence_number != stage.sequence_number:
        old, new = stage.sequence_number, data.sequence_number
        _move_stage(db, task.id, stage, old, new)
        changes.append(f"moved from position {old} to {new}")

    db.flush()
    if changes:
        _audit(
            db, actor=actor, task=task, action="workflow.stage_updated",
            resource_type="task_stage", resource_id=stage.id,
            summary=f"Updated stage \"{stage.name}\": " + "; ".join(changes) + ".",
        )
    sync_task_percent(db, task)
    return stage


def delete_stage(db: Session, actor: User, task_id: uuid.UUID, stage_id: uuid.UUID) -> None:
    task = task_service.get_task_for_actor(db, actor, task_id, Operation.MANAGE_WORKFLOW)
    _ensure_task_editable(task)
    stage = _load_stage(db, task.id, stage_id)

    if _enum_value(stage.status) not in {"pending", "cancelled"}:
        raise ConflictError(
            "Only pending or cancelled stages can be deleted; cancel or "
            "complete the stage to preserve its history.",
            code="stage_not_deletable",
        )
    item_count = db.scalar(
        select(func.count()).where(WorkItem.stage_id == stage.id)
    )
    if item_count:
        raise ConflictError(
            "The stage still contains work items; remove them first.",
            code="stage_not_empty",
        )

    name, sequence = stage.name, stage.sequence_number
    db.execute(sa_delete(TaskStage).where(TaskStage.id == stage.id))
    _shift_sequences(db, TaskStage, TaskStage.task_id == task.id,
                     sequence + 1, -1)
    _audit(
        db, actor=actor, task=task, action="workflow.stage_deleted",
        resource_type="task_stage", resource_id=stage_id,
        summary=f"Deleted stage {sequence} \"{name}\" from the workflow.",
    )


def transition_stage(db: Session, actor: User, task_id: uuid.UUID,
                     stage_id: uuid.UUID, to_status: str, reason: str | None) -> TaskStage:
    task = task_service.get_task_for_actor(db, actor, task_id, Operation.MANAGE_WORKFLOW)
    stage = _load_stage(db, task.id, stage_id)
    current = _enum_value(stage.status)
    target = wf.validate_stage_transition(current, to_status, reason=reason)

    if target == "in_progress" and current == "pending":
        _ensure_task_executing(task)
        states = [
            wf.StageState(
                id=s.id, sequence_number=s.sequence_number,
                execution_mode=_enum_value(s.execution_mode),
                status=_enum_value(s.status),
            )
            for s in _task_stages(db, task)
        ]
        if not wf.stage_is_actionable(states, stage.id):
            raise wf.WorkflowTransitionError(
                "Sequential stages can only start once every earlier stage is "
                "completed or cancelled.",
                code="stage_not_actionable",
            )

    if target == "completed":
        items = [i for i in _task_items(db, task) if i.stage_id == stage.id]
        wf.stage_may_complete(_item_facts(items), {i.id for i in items})
        stage.completed_at = datetime.now(UTC)

    if target == "in_progress" and current == "completed":
        stage.completed_at = None
    if target == "pending":
        stage.completed_at = None

    stage.status = StageStatus(target)
    db.flush()

    verb = {
        "in_progress": "started" if current == "pending" else "reopened",
        "completed": "completed",
        "cancelled": "cancelled",
        "pending": "restored to pending",
    }[target]
    _audit(
        db, actor=actor, task=task, action="workflow.stage_transitioned",
        resource_type="task_stage", resource_id=stage.id,
        summary=f"Stage \"{stage.name}\" {verb}.",
        reason=reason,
        metadata={"from_status": current, "to_status": target},
    )
    sync_task_percent(db, task)
    return stage




# ---------------------------------------------------------------------------
# Work items
# ---------------------------------------------------------------------------

def create_item(db: Session, actor: User, task_id: uuid.UUID,
                stage_id: uuid.UUID, data) -> WorkItem:
    task = task_service.get_task_for_actor(db, actor, task_id, Operation.MANAGE_WORKFLOW)
    _ensure_task_editable(task)
    stage = _load_stage(db, task.id, stage_id)

    parent = None
    if data.parent_work_item_id is not None:
        parent = _load_item(db, task.id, data.parent_work_item_id)
        if _enum_value(parent.item_type) != "milestone":
            raise ValidationFailedError(
                "Subtasks can only be nested under milestones.",
                code="invalid_parent",
            )
        if parent.stage_id != stage.id:
            raise ValidationFailedError(
                "The parent milestone must belong to the same stage.",
                code="parent_stage_mismatch",
            )

    assignee_user = (
        _resolve_assignee(db, data.assigned_user_id)
        if data.assigned_user_id else None
    )

    if data.sequence_number is not None:
        _shift_sequences(db, WorkItem, WorkItem.stage_id == stage.id,
                         data.sequence_number, +1)
        sequence = data.sequence_number
    else:
        sequence = _next_sequence(db, WorkItem, WorkItem.stage_id == stage.id)

    item = WorkItem(
        task_id=task.id,
        stage_id=stage.id,
        parent_work_item_id=parent.id if parent else None,
        item_type=WorkItemType(data.item_type.value),
        title=data.title.strip(),
        description=data.description,
        status=WorkItemStatus.pending,
        priority=data.priority,
        assigned_user_id=assignee_user.id if assignee_user else None,
        assigned_by_id=actor.id if assignee_user else None,
        assigned_at=datetime.now(UTC) if assignee_user else None,
        sequence_number=sequence,
        is_required=data.is_required,
        weight=data.weight,
        start_date=data.start_date,
        due_date=data.due_date,
        version=1,
    )
    if assignee_user is not None:
        item.assignee = assignee_user
    db.add(item)
    db.flush()
    type_label = "Milestone" if item.item_type == WorkItemType.milestone else "Subtask"
    _audit(
        db, actor=actor, task=task, action="workflow.item_created",
        resource_type="work_item", resource_id=item.id,
        summary=f"Added {type_label.lower()} \"{item.title}\" to stage "
                f"\"{stage.name}\".",
        metadata={"item_type": _enum_value(item.item_type),
                  "is_required": item.is_required},
    )
    sync_task_percent(db, task)
    return item


def _resolve_assignee(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise ValidationFailedError("Assigned user not found.", code="assignee_not_found")
    status = _enum_value(user.account_status)
    if status != "active":
        raise ValidationFailedError(
            "Work items can only be assigned to active users.",
            code="assignee_inactive",
        )
    return user


def update_item(db: Session, actor: User, task_id: uuid.UUID,
                item_id: uuid.UUID, data) -> WorkItem:
    task = task_service.get_task_for_actor(db, actor, task_id, Operation.MANAGE_WORKFLOW)
    _ensure_task_editable(task)
    item = _load_item(db, task.id, item_id)

    if int(item.version) != int(data.version):
        raise ConflictError(
            "This work item was modified by someone else. Refresh and retry "
            "(optimistic concurrency).",
            code="version_conflict",
        )

    changes: list[str] = []
    if data.title is not None and data.title.strip() != item.title:
        changes.append(f"renamed to \"{data.title.strip()}\"")
        item.title = data.title.strip()
    if data.description is not None:
        item.description = data.description
    if data.priority is not None:
        item.priority = data.priority
    if data.is_required is not None and data.is_required != item.is_required:
        item.is_required = data.is_required
        changes.append("marked required" if data.is_required else "marked optional")
    if data.weight is not None and data.weight != item.weight:
        item.weight = data.weight
        changes.append(f"weight set to {data.weight}")
    if data.start_date is not None:
        item.start_date = data.start_date
    if data.due_date is not None:
        item.due_date = data.due_date
    if item.start_date and item.due_date and item.due_date < item.start_date:
        raise ValidationFailedError("due_date cannot be before start_date.")

    if data.sequence_number is not None and data.sequence_number != item.sequence_number:
        old, new = item.sequence_number, data.sequence_number
        _move_item(db, item, old, new)
        changes.append(f"moved from position {old} to {new}")

    item.version += 1
    db.flush()
    if changes:
        _audit(
            db, actor=actor, task=task, action="workflow.item_updated",
            resource_type="work_item", resource_id=item.id,
            summary=f"Updated work item \"{item.title}\": " + "; ".join(changes) + ".",
        )
    sync_task_percent(db, task)
    return item


def delete_item(db: Session, actor: User, task_id: uuid.UUID, item_id: uuid.UUID) -> None:
    task = task_service.get_task_for_actor(db, actor, task_id, Operation.MANAGE_WORKFLOW)
    _ensure_task_editable(task)
    item = _load_item(db, task.id, item_id)

    if _enum_value(item.status) not in {"pending", "cancelled"}:
        raise ConflictError(
            "Only pending or cancelled work items can be deleted; cancel it to "
            "preserve completion history.",
            code="item_not_deletable",
        )
    edges = load_edges(db, task.id)
    if wf.would_orphan_item(edges, item.id) or any(
        e.successor_id == item.id for e in edges
    ):
        raise ConflictError(
            "Remove the dependencies that reference this work item first.",
            code="item_has_dependencies",
        )
    if db.scalar(select(func.count()).where(WorkItem.parent_work_item_id == item.id)):
        raise ConflictError(
            "The milestone still has subtasks; remove them first.",
            code="item_has_subtasks",
        )

    title = item.title
    db.execute(sa_delete(WorkItem).where(WorkItem.id == item.id))
    _shift_sequences(db, WorkItem, WorkItem.stage_id == item.stage_id,
                     item.sequence_number + 1, -1)
    _audit(
        db, actor=actor, task=task, action="workflow.item_deleted",
        resource_type="work_item", resource_id=item_id,
        summary=f"Deleted work item \"{title}\".",
    )
    sync_task_percent(db, task)


def transition_item(db: Session, actor: User, task_id: uuid.UUID,
                    item_id: uuid.UUID, to_status: str, reason: str | None) -> WorkItem:
    task = task_service.get_task_for_actor(
        db, actor, task_id,
        Operation.CANCEL if to_status == "cancelled" else Operation.COMPLETE,
    )
    item = _load_item(db, task.id, item_id)
    current = _enum_value(item.status)
    target = wf.validate_work_item_transition(current, to_status, reason=reason)

    if target == "in_progress" and current == "pending":
        _ensure_task_executing(task)
        edges = load_edges(db, task.id)
        statuses = {i.id: _enum_value(i.status) for i in _task_items(db, task)}
        unmet = wf.unmet_predecessors(edges, statuses, item.id)
        if unmet:
            raise wf.WorkflowTransitionError(
                f"This work item is blocked by {len(unmet)} incomplete "
                "predecessor(s); they must complete first.",
                code="item_blocked",
            )

    if target == "completed":
        _ensure_task_executing(task)
        facts = _item_facts(_task_items(db, task))
        wf.item_may_complete(facts, item.id)
        item.completed_at = datetime.now(UTC)

    if target in {"in_progress", "pending"}:
        item.completed_at = None

    item.status = WorkItemStatus(target)
    item.version += 1
    db.flush()

    verb = {
        "in_progress": "started" if current == "pending" else "reopened",
        "completed": "completed",
        "cancelled": "cancelled",
        "pending": "restored to pending",
    }[target]
    _audit(
        db, actor=actor, task=task, action="workflow.item_transitioned",
        resource_type="work_item", resource_id=item.id,
        summary=f"Work item \"{item.title}\" {verb}.",
        reason=reason,
        metadata={"from_status": current, "to_status": target},
    )

    # Completion cascade: a milestone auto-completes when its last required
    # subtask completes; reopening a subtask reopens a completed milestone.
    if item.parent_work_item_id:
        parent = db.get(WorkItem, item.parent_work_item_id)
        if parent is not None:
            parent_status = _enum_value(parent.status)
            facts = _item_facts(_task_items(db, task))
            if (
                target == "completed"
                and parent_status != "completed"
                and milestone_effectively_complete(facts, next(f for f in facts if f.id == parent.id))
            ):
                parent.status = WorkItemStatus.completed
                parent.completed_at = datetime.now(UTC)
                parent.version += 1
                _audit(
                    db, actor=actor, task=task, action="workflow.item_transitioned",
                    resource_type="work_item", resource_id=parent.id,
                    summary=f"Milestone \"{parent.title}\" auto-completed: all "
                            "required subtasks are done.",
                    metadata={"from_status": parent_status, "to_status": "completed",
                              "auto": True},
                )
            elif target in {"in_progress", "pending"} and parent_status == "completed":
                parent.status = WorkItemStatus.in_progress
                parent.completed_at = None
                parent.version += 1
                _audit(
                    db, actor=actor, task=task, action="workflow.item_transitioned",
                    resource_type="work_item", resource_id=parent.id,
                    summary=f"Milestone \"{parent.title}\" reopened because "
                            f"subtask \"{item.title}\" was {verb}.",
                    metadata={"from_status": "completed", "to_status": "in_progress",
                              "auto": True},
                )

    sync_task_percent(db, task)
    return item


def assign_item(db: Session, actor: User, task_id: uuid.UUID,
                item_id: uuid.UUID, assigned_user_id: uuid.UUID | None) -> WorkItem:
    task = task_service.get_task_for_actor(db, actor, task_id, Operation.MANAGE_WORKFLOW)
    item = _load_item(db, task.id, item_id)

    if assigned_user_id is None:
        previous = item.assignee.full_name if item.assignee else None
        item.assignee = None
        item.assigned_user_id = None
        item.assigned_by_id = None
        item.assigned_at = None
        item.version += 1
        db.flush()
        if previous:
            _audit(db, actor=actor, task=task, action="workflow.item_assigned",
                   resource_type="work_item", resource_id=item.id,
                   summary=f"Unassigned user {previous} from \"{item.title}\".")
        return item

    assignee = _resolve_assignee(db, assigned_user_id)
    item.assignee = assignee
    item.assigned_user_id = assignee.id
    item.assigned_by_id = actor.id
    item.assigned_at = datetime.now(UTC)
    item.version += 1
    db.flush()
    _audit(
        db, actor=actor, task=task, action="workflow.item_assigned",
        resource_type="work_item", resource_id=item.id,
        summary=f"Assigned \"{item.title}\" to {assignee.full_name}.",
        metadata={"assigned_user_id": str(assignee.id)},
    )
    return item


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

def add_dependency(db: Session, actor: User, task_id: uuid.UUID, data):
    task = task_service.get_task_for_actor(db, actor, task_id, Operation.MANAGE_WORKFLOW)
    _ensure_task_editable(task)

    predecessor = _load_item(db, task.id, data.predecessor_id)
    successor = _load_item(db, task.id, data.successor_id)

    edges = load_edges(db, task.id)
    try:
        wf.validate_dependency(
            edges, predecessor_id=predecessor.id, successor_id=successor.id
        )
    except wf.WorkflowTransitionError:
        raise  # already the domain error the API layer maps to HTTP

    dependency = WorkItemDependency(
        task_id=task.id,
        predecessor_id=predecessor.id,
        successor_id=successor.id,
        note=data.note,
        created_by_id=actor.id,
    )
    db.add(dependency)
    db.flush()
    _audit(
        db, actor=actor, task=task, action="workflow.dependency_added",
        resource_type="work_item_dependency", resource_id=dependency.id,
        summary=f"Added dependency: \"{successor.title}\" is blocked until "
                f"\"{predecessor.title}\" completes.",
        metadata={"predecessor_id": str(predecessor.id),
                  "successor_id": str(successor.id)},
    )
    return dependency


def remove_dependency(db: Session, actor: User, task_id: uuid.UUID,
                      dependency_id: uuid.UUID) -> None:
    task = task_service.get_task_for_actor(db, actor, task_id, Operation.MANAGE_WORKFLOW)
    dependency = db.scalar(
        select(WorkItemDependency).where(
            WorkItemDependency.id == dependency_id,
            WorkItemDependency.task_id == task.id,
        )
    )
    if dependency is None:
        raise NotFoundError("Dependency not found.")
    predecessor = db.get(WorkItem, dependency.predecessor_id)
    successor = db.get(WorkItem, dependency.successor_id)
    db.execute(sa_delete(WorkItemDependency).where(WorkItemDependency.id == dependency.id))
    _audit(
        db, actor=actor, task=task, action="workflow.dependency_removed",
        resource_type="work_item_dependency", resource_id=dependency_id,
        summary=f"Removed dependency between \"{predecessor.title if predecessor else '?'}\" "
                f"and \"{successor.title if successor else '?'}\".",
    )


# ---------------------------------------------------------------------------
# Progress mode (AC-06)
# ---------------------------------------------------------------------------

def set_progress_mode(db: Session, actor: User, task_id: uuid.UUID,
                      progress_mode: str, reason: str | None) -> Task:
    task = task_service.get_task_for_actor(db, actor, task_id, Operation.MANAGE_WORKFLOW)
    current = _enum_value(task.progress_mode)
    if progress_mode == current:
        return task

    task.progress_mode = progress_mode
    if progress_mode == "calculated":
        sync_task_percent(db, task)
        summary = "Task progress switched to calculated from the workflow."
    else:
        summary = "Task progress switched to manual entry."
    db.flush()
    _audit(
        db, actor=actor, task=task, action="workflow.progress_mode_changed",
        resource_type="task", resource_id=task.id,
        summary=summary, reason=reason,
        metadata={"from_mode": current, "to_mode": progress_mode},
    )
    return task


# ---------------------------------------------------------------------------
# Templates (Administration; gated by tasks.manage_all at the API layer)
# ---------------------------------------------------------------------------

def _definition_to_dict(stages) -> dict:
    return {
        "stages": [
            {
                "name": s.name,
                "execution_mode": s.execution_mode.value,
                "weight": s.weight,
                "items": [
                    {
                        "item_type": i.item_type.value,
                        "title": i.title,
                        "is_required": i.is_required,
                        "weight": i.weight,
                    }
                    for i in s.items
                ],
            }
            for s in stages
        ]
    }


def list_templates(db: Session) -> list[WorkflowTemplate]:
    return list(
        db.scalars(
            select(WorkflowTemplate)
            .where(WorkflowTemplate.is_active.is_(True))
            .order_by(WorkflowTemplate.name)
        )
    )


def create_template(db: Session, actor: User, data) -> WorkflowTemplate:
    existing = db.scalar(select(WorkflowTemplate).where(WorkflowTemplate.name == data.name))
    if existing is not None:
        raise ConflictError("A workflow template with this name already exists.",
                            code="template_name_taken")
    template = WorkflowTemplate(
        name=data.name.strip(),
        description=data.description,
        definition=_definition_to_dict(data.stages),
        version=1,
        created_by_id=actor.id,
        is_active=True,
    )
    db.add(template)
    db.flush()
    audit_service.record_audit_event(
        db, action="workflow.template_created", resource_type="workflow_template",
        resource_id=template.id, actor=actor,
        change_summary=f"Created workflow template \"{template.name}\".",
    )
    return template


def update_template(db: Session, actor: User, template_id: uuid.UUID, data) -> WorkflowTemplate:
    template = db.get(WorkflowTemplate, template_id)
    if template is None or not template.is_active:
        raise NotFoundError("Workflow template not found.")
    if data.name is not None and data.name != template.name:
        clash = db.scalar(select(WorkflowTemplate).where(WorkflowTemplate.name == data.name))
        if clash is not None:
            raise ConflictError("A workflow template with this name already exists.",
                                code="template_name_taken")
        template.name = data.name
    if data.description is not None:
        template.description = data.description
    if data.stages is not None:
        template.definition = _definition_to_dict(data.stages)
        template.version += 1
    if data.is_active is not None:
        template.is_active = data.is_active
    db.flush()
    audit_service.record_audit_event(
        db, action="workflow.template_updated", resource_type="workflow_template",
        resource_id=template.id, actor=actor,
        change_summary=f"Updated workflow template \"{template.name}\".",
    )
    return template
