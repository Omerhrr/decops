"""Task access policy engine (spec task_visibility; Phase 3 deliverable).

Pure domain logic — no database or framework imports — so the rules are unit
testable and reusable by any persistence layer (tasks arrive in Phase 4).

Design invariants (spec task_visibility.rules):
- Every task has an explicit access policy (mode is mandatory).
- Access to one task NEVER authorizes another task: evaluation is strictly
  per-task; grants are task-scoped by construction (the policy carries the
  task id and only its own grants).
- Access to a task does not automatically authorize every operation on it:
  each operation is checked against the operation matrix.
- Explicit grants override visibility scoping; explicit denials override
  grants (deny > grant > scope > admin).
- Revoked access takes effect immediately: the engine is stateless and is
  always evaluated against the *current* actor context at request time.
"""

from __future__ import annotations

import enum
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field


class VisibilityMode(str, enum.Enum):
    """The four visibility modes defined by the spec."""

    PRIVATE = "private"
    PARTICIPANTS = "participants"
    DEPARTMENT_SCOPED = "department_scoped"
    CUSTOM = "custom"


class Operation(str, enum.Enum):
    """Operations the engine can authorize on a task (and its nested resources)."""

    VIEW = "view"
    UPDATE = "update"
    ASSIGN = "assign"
    COMMENT = "comment"
    ATTACH = "attach"
    REVIEW = "review"
    MANAGE_WORKFLOW = "manage_workflow"
    CHANGE_VISIBILITY = "change_visibility"
    COMPLETE = "complete"
    CANCEL = "cancel"
    ARCHIVE = "archive"


class AccessDecision(str, enum.Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True)
class ActorContext:
    """What the engine knows about the acting user at evaluation time.

    Everything is captured as plain identifiers/sets so the engine can be
    evaluated with freshly loaded state on every request (immediate revocation).
    """

    user_id: uuid.UUID
    permission_codes: frozenset[str] = field(default_factory=frozenset)
    department_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)
    is_privileged_admin: bool = False  # holds tasks.manage_all (see ADMIN_BYPASS_PERMISSION)


# The single permission that permits an administrator to bypass visibility.
# "Permitted administrators" (spec): not all admins, only holders of this code.
ADMIN_BYPASS_PERMISSION = "tasks.manage_all"
# Permissions that grant view regardless of scoping in department_scoped mode.
DEPARTMENT_VIEW_PERMISSIONS = frozenset({"tasks.view_department", "tasks.manage_all"})


@dataclass(frozen=True)
class AccessPolicy:
    """The explicit, self-contained access policy of exactly one task.

    Grants/denials are embedded in the policy — they can never leak to other
    tasks because a policy is only ever constructed for a single task id.

    grant_levels maps user_id -> "view" | "operate" | "manage". Grants without
    a recorded level default to "operate" (Phase 3 binary-grant behaviour).
    """

    task_id: uuid.UUID
    mode: VisibilityMode
    # Private/participants: who is explicitly part of the circle.
    participant_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)
    creator_id: uuid.UUID | None = None
    # department_scoped: departments whose members with the view permission see it.
    department_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)
    # custom/any: explicit per-user grants and denials (revocable, audited upstream).
    explicit_grants: frozenset[uuid.UUID] = field(default_factory=frozenset)
    explicit_denials: frozenset[uuid.UUID] = field(default_factory=frozenset)
    grant_levels: Mapping[uuid.UUID, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.mode, VisibilityMode):
            raise ValueError(f"Access policy mode must be a VisibilityMode, got {self.mode!r}")


class AccessDeniedError(PermissionError):
    """Raised when an operation is not authorized on a task."""

    def __init__(self, task_id: uuid.UUID, operation: Operation, reason: str) -> None:
        self.task_id = task_id
        self.operation = operation
        self.reason = reason
        super().__init__(f"Access denied for {operation.value} on task {task_id}: {reason}")


# Operations a "view"-level grant permits (read/contribute only).
GRANT_VIEW_OPERATIONS = frozenset({Operation.VIEW, Operation.COMMENT, Operation.ATTACH})


def _can_view_scope(actor: ActorContext, policy: AccessPolicy) -> bool:
    """Visibility-scope check (no explicit grants involved)."""
    if policy.mode is VisibilityMode.PRIVATE:
        circle = set(policy.participant_ids)
        if policy.creator_id:
            circle.add(policy.creator_id)
        return actor.user_id in circle

    if policy.mode is VisibilityMode.PARTICIPANTS:
        return actor.user_id in policy.participant_ids

    if policy.mode is VisibilityMode.DEPARTMENT_SCOPED:
        if actor.user_id in policy.participant_ids:
            return True
        if not (actor.department_ids & policy.department_ids):
            return False
        # Department membership alone is not enough: the member must hold the
        # department view permission (spec: "subject to explicit restrictions").
        return bool(actor.permission_codes & DEPARTMENT_VIEW_PERMISSIONS)

    # CUSTOM: only explicit grants (checked by the caller) — scope grants nothing.
    return False


def evaluate_access(actor: ActorContext, policy: AccessPolicy, operation: Operation) -> AccessDecision:
    """Decide whether `actor` may perform `operation` on the task `policy` describes.

    Precedence (most to least restrictive):
      1. explicit denial  -> DENY
      2. manage_all admin -> ALLOW for view/admin operations
      3. explicit grant   -> ALLOW
      4. creator          -> ALLOW for everything except change_visibility without grant
      5. visibility scope -> ALLOW for view; members may update per matrix
    """
    # 1. Explicit denial always wins (revocation takes effect immediately).
    if actor.user_id in policy.explicit_denials:
        return AccessDecision.DENY

    is_admin = actor.is_privileged_admin and ADMIN_BYPASS_PERMISSION in actor.permission_codes
    if is_admin:
        # Permitted administrators can see and administer, but visibility
        # changes themselves still require the dedicated permission.
        if operation is Operation.CHANGE_VISIBILITY:
            return AccessDecision.ALLOW if "tasks.update_assigned" in actor.permission_codes else AccessDecision.DENY
        return AccessDecision.ALLOW

    # 2. Explicit per-user grant (custom mode and exceptions on any mode).
    if actor.user_id in policy.explicit_grants:
        level = policy.grant_levels.get(actor.user_id, "operate")
        if level == "view":
            # Read/contribute grant: access must not automatically authorize
            # every operation (spec task_visibility.rules).
            return AccessDecision.ALLOW if operation in GRANT_VIEW_OPERATIONS else AccessDecision.DENY
        if operation is Operation.MANAGE_WORKFLOW:
            # Restructuring the workflow (stages, items, dependencies) is a
            # manage-level power; operate grants execute work on items but
            # cannot restructure (Phase 5).
            return AccessDecision.ALLOW if level == "manage" else AccessDecision.DENY
        if operation is Operation.CHANGE_VISIBILITY:
            # Changing visibility requires explicit permission (spec rule).
            return AccessDecision.ALLOW if "tasks.update_assigned" in actor.permission_codes else AccessDecision.DENY
        if operation is Operation.ARCHIVE:
            return AccessDecision.DENY  # archiving is administrative only
        return AccessDecision.ALLOW

    # 3. Creator manages their task, within their permission limits.
    if policy.creator_id and actor.user_id == policy.creator_id:
        if operation is Operation.CHANGE_VISIBILITY:
            return AccessDecision.ALLOW if "tasks.update_assigned" in actor.permission_codes else AccessDecision.DENY
        if operation in {Operation.VIEW, Operation.UPDATE, Operation.ASSIGN, Operation.COMMENT,
                         Operation.ATTACH, Operation.REVIEW, Operation.MANAGE_WORKFLOW,
                         Operation.COMPLETE, Operation.CANCEL}:
            return AccessDecision.ALLOW
        return AccessDecision.DENY  # e.g. archive is admin-only

    # 4. Visibility scope: grants view; operation matrix for members.
    if _can_view_scope(actor, policy):
        if operation is Operation.VIEW:
            return AccessDecision.ALLOW
        if operation in {Operation.UPDATE, Operation.ASSIGN, Operation.MANAGE_WORKFLOW,
                         Operation.CHANGE_VISIBILITY}:
            # Full edit powers need the permission; participants without it can
            # still contribute (comment/attach/complete) but cannot restructure.
            return AccessDecision.ALLOW if "tasks.update_assigned" in actor.permission_codes else AccessDecision.DENY
        if operation in {Operation.COMMENT, Operation.ATTACH, Operation.COMPLETE}:
            return AccessDecision.ALLOW
        return AccessDecision.DENY  # review/cancel/archive need explicit grants

    return AccessDecision.DENY


def require_access(actor: ActorContext, policy: AccessPolicy, operation: Operation) -> None:
    """Raise AccessDeniedError when the operation is not authorized."""
    decision = evaluate_access(actor, policy, operation)
    if decision is not AccessDecision.ALLOW:
        if actor.user_id in policy.explicit_denials:
            reason = "access explicitly revoked"
        elif policy.mode is VisibilityMode.PRIVATE:
            reason = "task is private and you are not a participant"
        elif policy.mode is VisibilityMode.PARTICIPANTS:
            reason = "task is limited to its participants"
        elif policy.mode is VisibilityMode.DEPARTMENT_SCOPED:
            reason = "task is department-scoped and you lack the required department access"
        else:
            reason = "no explicit grant for this task"
        raise AccessDeniedError(policy.task_id, operation, reason)


def validate_policy(policy: AccessPolicy) -> list[str]:
    """Structural validation for "task creation must establish a valid policy".

    Returns a list of human-readable problems; empty list means valid.
    """
    problems: list[str] = []
    if not isinstance(policy.mode, VisibilityMode):
        problems.append("visibility mode must be one of private/participants/department_scoped/custom")

    if policy.mode is VisibilityMode.PRIVATE and not (policy.participant_ids or policy.creator_id):
        problems.append("private task must list at least one participant or a creator")

    if policy.mode is VisibilityMode.DEPARTMENT_SCOPED and not policy.department_ids:
        problems.append("department_scoped task must name at least one department")

    if policy.mode is VisibilityMode.CUSTOM and not policy.explicit_grants:
        problems.append("custom task must include at least one explicit grant")

    illegal = set(policy.explicit_denials) & set(policy.explicit_grants)
    if illegal:
        problems.append(f"users cannot be both granted and denied: {sorted(str(u) for u in illegal)}")
    return problems


def nested_resource_access(
    actor: ActorContext, task_policy: AccessPolicy, operation: Operation, *,
    stricter_nested: bool = False,
) -> AccessDecision:
    """Nested resources (comments, attachments, workflow items) inherit the
    task restrictions unless a more restrictive policy applies (spec rule)."""
    decision = evaluate_access(actor, task_policy, operation)
    if stricter_nested and operation is not Operation.VIEW:
        # Example of a more restrictive nested policy: no archive on children.
        if operation is Operation.ARCHIVE:
            return AccessDecision.DENY
    return decision
