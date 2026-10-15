"""Task management service (MOD-003, Phase 4).

Every read and mutation flows through the access-policy engine with freshly
loaded actor state (immediate revocation), the assignment policy (DEC-02,
active assignees, department scoping), and the lifecycle state machine
(reason-required transitions). All mutations are audited AND recorded on the
task's activity timeline (AC-12).

Authorization failures surface as 404 (not 403) so the API never confirms the
existence of restricted tasks (spec api conventions + AC-10).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.domain import assignment_policy, access_policy
from app.domain.access_policy import AccessPolicy, ActorContext, Operation, VisibilityMode
from app.domain.assignment_policy import AssignmentRole, AssignmentRole as AssignmentRoleEnum
from app.domain.task_lifecycle import TaskStatus, validate_transition
from app.models import (
    AccessLevel,
    AssignmentRoleType,
    Department,
    DepartmentMembership,
    ParticipationType,
    ProgressMode,
    Task,
    TaskAccessGrant,
    TaskActivity,
    TaskAssignment,
    TaskDepartment,
    TaskPriority,
    User,
)
from app.services import audit_service


class TaskError(Exception):
    def __init__(self, message: str, *, code: str = "task_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def _enum_value(value) -> str:
    """String() columns may load back as plain strings or str-enums depending
    on the driver - normalize before comparing or summarizing."""
    return value.value if hasattr(value, "value") else str(value)


# ---------------------------------------------------------------------------
# Authorization plumbing
# ---------------------------------------------------------------------------

def get_user_permission_codes(db: Session, user: User) -> set[str]:
    """Global permission codes for the user (mirrors api.deps logic)."""
    codes: set[str] = set()
    for user_role in user.roles:
        if user_role.scope_type != "global":
            continue
        for link in user_role.role.permissions:
            codes.add(link.permission.code)
    return codes


def build_actor_context(db: Session, user: User) -> ActorContext:
    """Fresh actor context per request — revoked access applies immediately."""
    return ActorContext(
        user_id=user.id,
        permission_codes=frozenset(get_user_permission_codes(db, user)),
        department_ids=frozenset(m.department_id for m in user.memberships),
        is_privileged_admin="tasks.manage_all" in get_user_permission_codes(db, user),
    )


def build_policy(db: Session, task: Task) -> AccessPolicy:
    """Assemble the task's explicit, self-contained policy from current state."""
    participant_ids = {
        a.user_id for a in task.assignments
        if a.revoked_at is None
    }
    participant_ids.add(task.created_by_id)
    grant_rows = [g for g in task.access_grants if g.revoked_at is None]
    return AccessPolicy(
        task_id=task.id,
        mode=VisibilityMode(task.visibility_mode),
        participant_ids=frozenset(participant_ids),
        creator_id=task.created_by_id,
        department_ids=frozenset(td.department_id for td in task.task_departments),
        explicit_grants=frozenset(
            g.principal_id for g in grant_rows if g.access_level != AccessLevel.denied
        ),
        explicit_denials=frozenset(
            g.principal_id for g in grant_rows if g.access_level == AccessLevel.denied
        ),
        grant_levels={
            g.principal_id: _enum_value(g.access_level)
            for g in grant_rows if g.access_level != AccessLevel.denied
        },
    )


def get_task(db: Session, task_id: uuid.UUID) -> Task | None:
    return db.scalar(
        select(Task)
        .options(
            joinedload(Task.accountable_pm),
            joinedload(Task.created_by),
            joinedload(Task.assignments).joinedload(TaskAssignment.user),
            joinedload(Task.assignments).joinedload(TaskAssignment.assigned_by),
            joinedload(Task.task_departments).joinedload(TaskDepartment.department),
            joinedload(Task.access_grants).joinedload(TaskAccessGrant.principal),
            joinedload(Task.access_grants).joinedload(TaskAccessGrant.granted_by),
        )
        .where(Task.id == task_id)
    )


def get_task_for_actor(db: Session, actor: User, task_id: uuid.UUID,
                       operation: Operation = Operation.VIEW) -> Task:
    """Load a task and enforce `operation`; deny => 404 (non-enumeration)."""
    task = get_task(db, task_id)
    if task is None:
        raise NotFoundError("Task not found.")
    try:
        access_policy.require_access(build_actor_context(db, actor), build_policy(db, task), operation)
    except access_policy.AccessDeniedError:
        raise NotFoundError("Task not found.") from None
    return task


def _require_permission_codes(actor: User, *codes: str) -> None:
    held = {link.permission.code for ur in actor.roles if ur.scope_type == "global"
            for link in ur.role.permissions}
    if not held & set(codes):
        raise NotFoundError("Task not found.")


# ---------------------------------------------------------------------------
# Activity timeline (AC-12, user-facing)
# ---------------------------------------------------------------------------

def record_activity(
    db: Session, *, task: Task, actor: User | None, activity_type: str,
    summary: str, detail: dict | None = None,
) -> TaskActivity:
    event = TaskActivity(
        task_id=task.id,
        actor_id=actor.id if actor else None,
        activity_type=activity_type,
        summary=summary[:500],
        detail=detail,
    )
    db.add(event)
    return event


# ---------------------------------------------------------------------------
# Task numbers
# ---------------------------------------------------------------------------

def _next_task_number(db: Session) -> str:
    year = datetime.now(UTC).year
    prefix = f"TSK-{year}-"
    count = int(db.scalar(
        select(func.count(Task.id)).where(Task.task_number.like(f"{prefix}%"))
    ) or 0)
    # Loop guards against gaps from deleted rows.
    for candidate in range(count + 1, count + 1000):
        number = f"{prefix}{candidate:04d}"
        exists = db.scalar(select(Task.id).where(Task.task_number == number)) is not None
        if not exists:
            return number
    raise TaskError("Unable to allocate a task number.", code="number_exhausted")


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def list_tasks_for_actor(
    db: Session,
    actor: User,
    *,
    status: str | None = None,
    priority: str | None = None,
    q: str | None = None,
    department_id: uuid.UUID | None = None,
    accountable_pm_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[Task], int]:
    """Authorization-aware listing: candidate rows filtered by scalar filters,
    then the access engine decides visibility per task (never the reverse).
    Spec: "Search, autocomplete, exports, dashboards, and reporting must apply
    authorization."""
    actor_ctx = build_actor_context(db, actor)

    stmt = select(Task).options(
        joinedload(Task.accountable_pm),
        joinedload(Task.task_departments).joinedload(TaskDepartment.department),
    )
    if status:
        try:
            stmt = stmt.where(Task.status == TaskStatus(status))
        except ValueError as exc:
            raise ValidationFailedError(f"Unknown status '{status}'.") from exc
    if priority:
        try:
            stmt = stmt.where(Task.priority == TaskPriority(priority))
        except ValueError as exc:
            raise ValidationFailedError(f"Unknown priority '{priority}'.") from exc
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            Task.title.ilike(like) | Task.task_number.ilike(like) | Task.description.ilike(like)
        )
    if accountable_pm_id:
        stmt = stmt.where(Task.accountable_pm_id == accountable_pm_id)
    if department_id:
        stmt = stmt.where(
            Task.task_departments.any(TaskDepartment.department_id == department_id)
        )

    stmt = stmt.order_by(Task.created_at.desc()).limit(2000)  # sandbox safety cap
    candidates = db.scalars(stmt).unique().all()

    visible = [
        t for t in candidates
        if access_policy.evaluate_access(actor_ctx, build_policy(db, t), Operation.VIEW)
        is access_policy.AccessDecision.ALLOW
    ]
    total = len(visible)
    start = (max(page, 1) - 1) * page_size
    return visible[start:start + page_size], total


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------

def create_task(
    db: Session,
    *,
    actor: User,
    title: str,
    accountable_pm_id: uuid.UUID,
    priority: TaskPriority = TaskPriority.medium,
    description: str | None = None,
    start_date=None,
    due_date=None,
    next_follow_up_date=None,
    dependency_summary: str | None = None,
    visibility_mode: str = "participants",
    progress_mode: ProgressMode = ProgressMode.manual,
    department_ids: list[uuid.UUID] | None = None,
    participation_type: ParticipationType = ParticipationType.executing,
    grant_user_ids: list[uuid.UUID] | None = None,
    grant_access_level: AccessLevel = AccessLevel.view,
    request_id: str | None = None,
) -> Task:
    """AC-01: authorized user creates a task with unique number, title,
    accountable PM, and due date. Creation establishes a valid access policy."""
    actor_ctx = build_actor_context(db, actor)

    pm = db.get(User, accountable_pm_id)
    if pm is None:
        raise ValidationFailedError("The selected accountable PM does not exist.")
    if pm.id != actor.id:
        # Assigning someone else goes through the assignment policy.
        assignment_policy.validate_assignment(
            actor_id=actor.id,
            actor_permission_codes=frozenset(get_user_permission_codes(db, actor)),
            target_role=AssignmentRoleEnum.ACCOUNTABLE_PM,
            assignee=assignment_policy.AssigneeProfile(
                user_id=pm.id,
                account_status=str(pm.account_status.value if hasattr(pm.account_status, "value") else pm.account_status),
                department_ids=frozenset(m.department_id for m in pm.memberships),
            ),
            context=assignment_policy.AssignmentContext(task_id=uuid.uuid4(), task_department_ids=frozenset()),
        )

    departments: list[Department] = []
    for dep_id in set(department_ids or []):
        dep = db.get(Department, dep_id)
        if dep is None:
            raise ValidationFailedError(f"Department {dep_id} does not exist.")
        departments.append(dep)

    grant_users: list[User] = []
    for uid in set(grant_user_ids or []):
        u = db.get(User, uid)
        if u is None:
            raise ValidationFailedError(f"Grant user {uid} does not exist.")
        grant_users.append(u)
    if grant_access_level == AccessLevel.denied and grant_users:
        raise ValidationFailedError("Cannot create a task with an explicit denial; remove the user instead.")

    # Validate the policy structurally BEFORE persisting (spec: "Task creation
    # must establish a valid access policy").
    draft_policy = AccessPolicy(
        task_id=uuid.uuid4(),
        mode=VisibilityMode(visibility_mode),
        participant_ids=frozenset({pm.id, actor.id}),
        creator_id=actor.id,
        department_ids=frozenset(d.id for d in departments),
        explicit_grants=frozenset(u.id for u in grant_users),
    )
    problems = access_policy.validate_policy(draft_policy)
    if problems:
        raise ValidationFailedError("Invalid access policy: " + "; ".join(problems))

    task = Task(
        task_number=_next_task_number(db),
        title=title.strip(),
        description=(description or "").strip() or None,
        priority=priority,
        status=TaskStatus.draft,
        accountable_pm_id=pm.id,
        created_by_id=actor.id,
        start_date=start_date,
        due_date=due_date,
        next_follow_up_date=next_follow_up_date,
        dependency_summary=(dependency_summary or "").strip() or None,
        visibility_mode=visibility_mode,
        progress_mode=progress_mode,
        version=1,
    )
    db.add(task)
    db.flush()

    db.add(TaskAssignment(
        task_id=task.id, user_id=pm.id,
        assignment_role=AssignmentRoleType.accountable_pm,
        assigned_by_id=actor.id,
    ))
    for dep in departments:
        db.add(TaskDepartment(
            task_id=task.id, department_id=dep.id, participation_type=participation_type,
        ))
    for u in grant_users:
        db.add(TaskAccessGrant(
            task_id=task.id, principal_id=u.id,
            access_level=grant_access_level, granted_by_id=actor.id,
        ))

    summary = f"Created task '{task.title}' ({task.task_number})"
    record_activity(db, task=task, actor=actor, activity_type="task.created",
                    summary=summary, detail={"visibility_mode": visibility_mode})
    audit_service.record_audit_event(
        db, action="task.created", resource_type="task", resource_id=task.id,
        actor=actor, request_id=request_id,
        change_summary=summary,
        metadata={"task_number": task.task_number, "visibility_mode": visibility_mode},
    )
    return task


def update_task(
    db: Session,
    *,
    actor: User,
    task: Task,
    expected_version: int,
    fields: dict,
    request_id: str | None = None,
) -> Task:
    """Permitted-field update with optimistic concurrency (AC-18).

    `fields` contains ONLY the keys the client actually sent (model_fields_set),
    so PATCH semantics distinguish "not sent" from "explicitly cleared".
    """
    if expected_version != task.version:
        raise ConflictError(
            "This task was modified by someone else. Reload and reapply your changes.",
            code="version_conflict",
        )
    changes: dict[str, dict] = {}

    def _changed(name: str, old, new) -> bool:
        return _serializable(old) != _serializable(new)

    # Non-nullable fields: only apply when a usable value was sent.
    if "title" in fields and fields["title"] is not None:
        new_title = str(fields["title"]).strip()
        if _changed("title", task.title, new_title):
            changes["title"] = {"from": task.title, "to": new_title}
            task.title = new_title
    if "priority" in fields and fields["priority"] is not None:
        new_priority = TaskPriority(fields["priority"])
        if new_priority.value != _enum_value(task.priority):
            changes["priority"] = {"from": _enum_value(task.priority), "to": new_priority.value}
            task.priority = new_priority
    if "progress_mode" in fields and fields["progress_mode"] is not None:
        new_mode = ProgressMode(fields["progress_mode"])
        if new_mode.value != _enum_value(task.progress_mode):
            changes["progress_mode"] = {"from": _enum_value(task.progress_mode), "to": new_mode.value}
            task.progress_mode = new_mode
    if "percent_complete" in fields and fields["percent_complete"] is not None:
        pct = int(fields["percent_complete"])
        if pct != task.percent_complete:
            changes["percent_complete"] = {"from": task.percent_complete, "to": pct}
            task.percent_complete = pct

    # Nullable fields: explicit None clears the value.
    for name in ("description", "dependency_summary"):
        if name in fields:
            new_value = (fields[name] or "").strip() or None if isinstance(fields[name], str) else fields[name]
            if _changed(name, getattr(task, name), new_value):
                changes[name] = {"from": _serializable(getattr(task, name)), "to": _serializable(new_value)}
                setattr(task, name, new_value)
    for name in ("start_date", "due_date", "next_follow_up_date"):
        if name in fields:
            new_value = fields[name]
            if _changed(name, getattr(task, name), new_value):
                changes[name] = {"from": _serializable(getattr(task, name)), "to": _serializable(new_value)}
                setattr(task, name, new_value)

    if not changes:
        return task

    task.version += 1  # AC-18: every writer bumps the version
    summary = f"Updated {', '.join(sorted(changes))} on '{task.title}'"
    record_activity(db, task=task, actor=actor, activity_type="task.updated",
                    summary=summary, detail={"changes": changes})
    audit_service.record_audit_event(
        db, action="task.updated", resource_type="task", resource_id=task.id,
        actor=actor, request_id=request_id, change_summary=summary,
        metadata={"changes": changes, "version": task.version},
    )
    return task


def _serializable(value):
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


# Operation required per lifecycle target (engine matrix, spec roles).
_TRANSITION_OPERATION = {
    TaskStatus.completed: Operation.COMPLETE,
    TaskStatus.cancelled: Operation.CANCEL,
    TaskStatus.archived: Operation.ARCHIVE,
}


def transition_task(
    db: Session,
    *,
    actor: User,
    task: Task,
    to_status: str,
    reason: str | None = None,
    request_id: str | None = None,
) -> Task:
    """Backend-validated, authorized lifecycle transition (spec transition_rules)."""
    from_status = TaskStatus(_enum_value(task.status))
    target = validate_transition(from_status, to_status, reason=reason)

    operation = _TRANSITION_OPERATION.get(target, Operation.UPDATE)
    try:
        access_policy.require_access(build_actor_context(db, actor), build_policy(db, task), operation)
    except access_policy.AccessDeniedError:
        raise NotFoundError("Task not found.") from None

    task.status = target
    now = datetime.now(UTC)
    if target is TaskStatus.completed:
        task.completed_at = now
    elif target is TaskStatus.cancelled:
        task.cancelled_at = now
    elif target is TaskStatus.archived:
        task.archived_at = now
    if target in (TaskStatus.open, TaskStatus.in_progress, TaskStatus.blocked,
                  TaskStatus.under_review):
        # Reopening/unblocking clears the terminal timestamps.
        task.completed_at = None
        task.cancelled_at = None
        task.archived_at = None
    task.version += 1

    summary = f"Moved '{task.title}' from {from_status.value} to {target.value}"
    if reason and reason.strip():
        summary += f" — {reason.strip()[:200]}"
    record_activity(db, task=task, actor=actor, activity_type="task.status_changed",
                    summary=summary,
                    detail={"from": from_status.value, "to": target.value,
                            "reason": (reason or "").strip() or None})
    audit_service.record_audit_event(
        db, action="task.status_changed", resource_type="task", resource_id=task.id,
        actor=actor, request_id=request_id, reason=(reason or "").strip() or None,
        change_summary=summary,
        metadata={"from_status": from_status.value, "to_status": target.value},
    )
    return task


def assign_user(
    db: Session,
    *,
    actor: User,
    task: Task,
    user_id: uuid.UUID,
    role: AssignmentRoleType,
    request_id: str | None = None,
) -> TaskAssignment:
    """Assign accountable/supporting PM through the assignment policy."""
    try:
        access_policy.require_access(
            build_actor_context(db, actor), build_policy(db, task), Operation.ASSIGN)
    except access_policy.AccessDeniedError:
        raise NotFoundError("Task not found.") from None

    assignee = db.get(User, user_id)
    if assignee is None:
        raise ValidationFailedError("The selected user does not exist.")

    context = assignment_policy.AssignmentContext(
        task_id=task.id,
        task_department_ids=frozenset(td.department_id for td in task.task_departments),
        current_accountable_pm=task.accountable_pm_id,
        current_supporting_pms=frozenset(
            a.user_id for a in task.assignments
            if a.revoked_at is None
            and AssignmentRoleType(_enum_value(a.assignment_role)) == AssignmentRoleType.supporting_pm
        ),
    )
    assignment_policy.validate_assignment(
        actor_id=actor.id,
        actor_permission_codes=frozenset(get_user_permission_codes(db, actor)),
        target_role=AssignmentRole(role.value),
        assignee=assignment_policy.AssigneeProfile(
            user_id=assignee.id,
            account_status=str(assignee.account_status.value if hasattr(assignee.account_status, "value") else assignee.account_status),
            department_ids=frozenset(m.department_id for m in assignee.memberships),
        ),
        context=context,
    )

    existing = db.scalar(select(TaskAssignment).where(
        TaskAssignment.task_id == task.id,
        TaskAssignment.user_id == user_id,
        TaskAssignment.assignment_role == AssignmentRoleType(role.value).value,
        TaskAssignment.revoked_at.is_(None),
    ))
    if existing is not None:
        raise ConflictError("This user already holds that assignment role.", code="already_assigned")

    if role == AssignmentRoleType.accountable_pm and task.accountable_pm_id != user_id:
        # DEC-02: revoke the previous accountable PM's assignment row.
        previous = db.scalars(select(TaskAssignment).where(
            TaskAssignment.task_id == task.id,
            TaskAssignment.assignment_role == AssignmentRoleType.accountable_pm.value,
            TaskAssignment.revoked_at.is_(None),
        )).all()
        for row in previous:
            row.revoked_at = datetime.now(UTC)
        # The new PM cannot remain a supporting PM simultaneously.
        for row in task.assignments:
            if (row.user_id == user_id and row.revoked_at is None
                    and AssignmentRoleType(_enum_value(row.assignment_role)) == AssignmentRoleType.supporting_pm):
                row.revoked_at = datetime.now(UTC)
        old_pm = task.accountable_pm
        task.accountable_pm_id = user_id
        task.version += 1
        record_activity(
            db, task=task, actor=actor, activity_type="task.accountable_pm_changed",
            summary=(f"Accountable PM changed from {old_pm.full_name if old_pm else '—'} "
                     f"to {assignee.full_name}"),
            detail={"from": str(old_pm.id) if old_pm else None, "to": str(user_id)},
        )
        audit_service.record_audit_event(
            db, action="task.accountable_pm_changed", resource_type="task", resource_id=task.id,
            actor=actor, request_id=request_id,
            change_summary=f"Accountable PM changed to {assignee.full_name}",
            metadata={"from": str(old_pm.id) if old_pm else None, "to": str(user_id)},
        )

    assignment = TaskAssignment(
        task_id=task.id, user_id=user_id,
        assignment_role=AssignmentRoleType(role.value),
        assigned_by_id=actor.id,  # MOD-003: record the assigning user
    )
    db.add(assignment)
    db.flush()

    summary = f"Assigned {assignee.full_name} as {role.value.replace('_', ' ')}"
    record_activity(db, task=task, actor=actor, activity_type="task.assigned",
                    summary=summary, detail={"user_id": str(user_id), "role": role.value})
    audit_service.record_audit_event(
        db, action="task.assigned", resource_type="task", resource_id=task.id,
        actor=actor, request_id=request_id, change_summary=summary,
        metadata={"assignee": str(user_id), "role": role.value},
    )
    return assignment


def revoke_assignment(
    db: Session,
    *,
    actor: User,
    task: Task,
    assignment_id: uuid.UUID,
    request_id: str | None = None,
) -> None:
    try:
        access_policy.require_access(
            build_actor_context(db, actor), build_policy(db, task), Operation.ASSIGN)
    except access_policy.AccessDeniedError:
        raise NotFoundError("Task not found.") from None

    assignment = db.get(TaskAssignment, assignment_id)
    if assignment is None or assignment.task_id != task.id or assignment.revoked_at is not None:
        raise NotFoundError("Assignment not found.")
    if (AssignmentRoleType(_enum_value(assignment.assignment_role)) == AssignmentRoleType.accountable_pm
            and assignment.user_id == task.accountable_pm_id):
        raise ConflictError(
            "Replace the accountable PM instead of revoking the only accountability.",
            code="accountable_pm_required",
        )
    assignment.revoked_at = datetime.now(UTC)
    task.version += 1

    assignee = db.get(User, assignment.user_id)
    summary = (f"Removed {assignee.full_name if assignee else assignment.user_id} "
               f"from {AssignmentRoleType(_enum_value(assignment.assignment_role)).value.replace('_', ' ')}")
    record_activity(db, task=task, actor=actor, activity_type="task.unassigned",
                    summary=summary, detail={"user_id": str(assignment.user_id)})
    audit_service.record_audit_event(
        db, action="task.unassigned", resource_type="task", resource_id=task.id,
        actor=actor, request_id=request_id, change_summary=summary,
        metadata={"assignee": str(assignment.user_id),
                  "role": _enum_value(assignment.assignment_role)},
    )


def add_department(
    db: Session, *, actor: User, task: Task, department_id: uuid.UUID,
    participation_type: ParticipationType = ParticipationType.executing,
    request_id: str | None = None,
) -> TaskDepartment:
    try:
        access_policy.require_access(
            build_actor_context(db, actor), build_policy(db, task), Operation.UPDATE)
    except access_policy.AccessDeniedError:
        raise NotFoundError("Task not found.") from None

    department = db.get(Department, department_id)
    if department is None:
        raise ValidationFailedError("The selected department does not exist.")
    exists = db.scalar(select(TaskDepartment).where(
        TaskDepartment.task_id == task.id,
        TaskDepartment.department_id == department_id,
    ))
    if exists is not None:
        raise ConflictError("This department already participates in the task.", code="already_linked")

    link = TaskDepartment(
        task_id=task.id, department_id=department_id,
        participation_type=participation_type,
    )
    db.add(link)
    db.flush()
    task.version += 1
    summary = f"Linked department '{department.name}' ({participation_type.value})"
    record_activity(db, task=task, actor=actor, activity_type="task.department_added",
                    summary=summary, detail={"department_id": str(department_id)})
    audit_service.record_audit_event(
        db, action="task.department_added", resource_type="task", resource_id=task.id,
        actor=actor, request_id=request_id, change_summary=summary,
        metadata={"department_id": str(department_id)},
    )
    return link


def add_access_grant(
    db: Session, *, actor: User, task: Task, user_id: uuid.UUID,
    access_level: AccessLevel, request_id: str | None = None,
) -> TaskAccessGrant:
    """Grant (or explicitly deny) a user; requires the visibility-change
    operation and produces an audit event (spec task_visibility.rules)."""
    try:
        access_policy.require_access(
            build_actor_context(db, actor), build_policy(db, task),
            Operation.CHANGE_VISIBILITY)
    except access_policy.AccessDeniedError:
        raise NotFoundError("Task not found.") from None

    target = db.get(User, user_id)
    if target is None:
        raise ValidationFailedError("The selected user does not exist.")

    existing = db.scalar(select(TaskAccessGrant).where(
        TaskAccessGrant.task_id == task.id,
        TaskAccessGrant.principal_id == user_id,
        TaskAccessGrant.revoked_at.is_(None),
    ))
    if existing is not None:
        raise ConflictError("This user already holds an active grant on the task.",
                            code="grant_exists")

    grant = TaskAccessGrant(
        task_id=task.id, principal_id=user_id,
        access_level=access_level, granted_by_id=actor.id,
    )
    db.add(grant)
    db.flush()
    task.version += 1
    action_label = "denied access to" if access_level == AccessLevel.denied else f"granted {access_level.value} access to"
    summary = f"{actor.full_name} {action_label} {target.full_name}"
    record_activity(db, task=task, actor=actor, activity_type="task.access_changed",
                    summary=summary,
                    detail={"user_id": str(user_id), "access_level": access_level.value})
    audit_service.record_audit_event(
        db, action="task.access_granted", resource_type="task", resource_id=task.id,
        actor=actor, request_id=request_id, change_summary=summary,
        metadata={"user_id": str(user_id), "access_level": access_level.value},
    )
    return grant


def revoke_access_grant(
    db: Session, *, actor: User, task: Task, grant_id: uuid.UUID,
    reason: str | None = None, request_id: str | None = None,
) -> None:
    try:
        access_policy.require_access(
            build_actor_context(db, actor), build_policy(db, task),
            Operation.CHANGE_VISIBILITY)
    except access_policy.AccessDeniedError:
        raise NotFoundError("Task not found.") from None

    grant = db.get(TaskAccessGrant, grant_id)
    if grant is None or grant.task_id != task.id or grant.revoked_at is not None:
        raise NotFoundError("Access grant not found.")
    grant.revoked_at = datetime.now(UTC)
    grant.revocation_reason = (reason or "").strip() or None
    task.version += 1

    target = db.get(User, grant.principal_id)
    summary = f"Revoked {target.full_name if target else grant.principal_id}'s access"
    record_activity(db, task=task, actor=actor, activity_type="task.access_changed",
                    summary=summary,
                    detail={"user_id": str(grant.principal_id),
                            "revocation_reason": grant.revocation_reason})
    audit_service.record_audit_event(
        db, action="task.access_revoked", resource_type="task", resource_id=task.id,
        actor=actor, request_id=request_id, reason=grant.revocation_reason,
        change_summary=summary, metadata={"user_id": str(grant.principal_id)},
    )


def list_activity(db: Session, task: Task) -> list[TaskActivity]:
    return list(db.scalars(
        select(TaskActivity)
        .options(joinedload(TaskActivity.actor))
        .where(TaskActivity.task_id == task.id)
        .order_by(TaskActivity.created_at.desc(), TaskActivity.id.desc())
        .limit(200)
    ).all())
