"""Assignment authorization (spec Phase 3: "Implement assignment authorization"
and MOD-003 "Assign one accountable project manager / supporting project managers").

Pure domain rules, enforced by the task API in Phase 4:
- The actor must hold an assignment permission appropriate for the target role.
- The assignee must be an active employee (deactivated accounts cannot take work).
- Exactly ONE accountable project manager per task (DEC-02); zero or multiple
  supporting PMs are fine.
- Department-scoped tasks may only take assignees from the participating
  departments (unless the actor holds tasks.manage_all).
- The actor who assigns is recorded (spec: "Record the assigning user").
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field


class AssignmentRole(str, enum.Enum):
    ACCOUNTABLE_PM = "accountable_pm"
    SUPPORTING_PM = "supporting_pm"
    WORK_ITEM_ASSIGNEE = "work_item_assignee"


class AssignmentDeniedError(ValueError):
    """Raised when an assignment violates the authorization rules."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


# Actor permission needed per assignment role (spec roles_and_permissions matrix).
ACTOR_PERMISSIONS: dict[AssignmentRole, frozenset[str]] = {
    AssignmentRole.ACCOUNTABLE_PM: frozenset({"tasks.update_assigned", "tasks.assign_department"}),
    AssignmentRole.SUPPORTING_PM: frozenset({"tasks.update_assigned", "tasks.assign_department"}),
    AssignmentRole.WORK_ITEM_ASSIGNEE: frozenset({"work_items.update_assigned", "tasks.update_assigned"}),
}

ADMIN_BYPASS_PERMISSION = "tasks.manage_all"


@dataclass(frozen=True)
class AssigneeProfile:
    """Current, freshly-loaded state of the candidate assignee."""

    user_id: uuid.UUID
    account_status: str  # "active" | "disabled" | "deactivated"
    permission_codes: frozenset[str] = field(default_factory=frozenset)
    department_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)


@dataclass(frozen=True)
class AssignmentContext:
    """Everything the assignment check needs about the task."""

    task_id: uuid.UUID
    task_department_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)
    current_accountable_pm: uuid.UUID | None = None
    current_supporting_pms: frozenset[uuid.UUID] = field(default_factory=frozenset)


def can_assign(
    actor_permission_codes: frozenset[str],
    target_role: AssignmentRole,
    assignee: AssigneeProfile,
    context: AssignmentContext,
) -> tuple[bool, str]:
    """Return (allowed, reason). Reason is '' when allowed."""
    needed = ACTOR_PERMISSIONS[target_role]
    if not (actor_permission_codes & needed) and ADMIN_BYPASS_PERMISSION not in actor_permission_codes:
        return False, f"actor lacks the permission to assign {target_role.value}"

    if assignee.account_status != "active":
        return False, "assignee account is not active"

    if context.task_department_ids and ADMIN_BYPASS_PERMISSION not in actor_permission_codes:
        if not (assignee.department_ids & context.task_department_ids):
            return False, "assignee does not belong to any department of this task"

    if target_role is AssignmentRole.ACCOUNTABLE_PM:
        # DEC-02: one accountable PM. Already holding accountability is a no-op
        # (allowed, idempotent); someone else holding it is a replacement and
        # is allowed - the caller records the change - but must be deliberate.
        pass
    return True, ""


def validate_assignment(
    actor_id: uuid.UUID,
    actor_permission_codes: frozenset[str],
    target_role: AssignmentRole,
    assignee: AssigneeProfile,
    context: AssignmentContext,
) -> str:
    """Validate and return the effective assigning user id for audit purposes.

    Raises AssignmentDeniedError when the assignment violates policy. The
    returned actor id must be persisted with the assignment (MOD-003: record
    the assigning user).
    """
    allowed, reason = can_assign(actor_permission_codes, target_role, assignee, context)
    if not allowed:
        raise AssignmentDeniedError(reason)

    if target_role is AssignmentRole.ACCOUNTABLE_PM and context.current_accountable_pm == assignee.user_id:
        # Idempotent re-assignment: nothing changes, keep original record.
        return str(actor_id)
    return str(actor_id)


def replace_accountable_pm(
    current: AssignmentContext,
    new_pm_id: uuid.UUID,
) -> AssignmentContext:
    """Return a new context with the accountable PM replaced (DEC-02: one PM)."""
    supporting = set(current.current_supporting_pms)
    supporting.discard(new_pm_id)  # cannot be accountable and supporting simultaneously
    return AssignmentContext(
        task_id=current.task_id,
        task_department_ids=current.task_department_ids,
        current_accountable_pm=new_pm_id,
        current_supporting_pms=frozenset(supporting),
    )
