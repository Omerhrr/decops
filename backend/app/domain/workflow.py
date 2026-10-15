"""Workflow domain logic (spec workflow_engine; Phase 5).

Pure domain rules - no database or framework imports - covering:

- Stage and work-item state machines (invalid transitions are rejected).
- Dependency graphs: cycle prevention ("Circular dependencies must be
  rejected"), duplicate/self edges, and blocker resolution ("Dependencies
  and blockers").
- Stage actionability for sequential/parallel/mixed execution
  ("Sequential stages become actionable according to predecessor
  completion; parallel stages may progress simultaneously").
- Completion rules for stages and milestones (required items gate
  completion; optional and cancelled items never block).

The service layer enforces authorization and persistence; this module owns
the *rules* so they can be unit tested exhaustively (Phase 5 exit criteria:
"Invalid transitions and dependency cycles are rejected").
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field


class WorkflowTransitionError(ValueError):
    """Raised when a workflow transition/operation violates the rules."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# State machines
# ---------------------------------------------------------------------------

STAGE_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"in_progress", "cancelled"}),
    "in_progress": frozenset({"completed", "cancelled"}),
    "completed": frozenset({"in_progress"}),   # reopen (reason required)
    "cancelled": frozenset({"pending"}),       # restore (reason required)
}

WORK_ITEM_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"in_progress", "cancelled"}),
    "in_progress": frozenset({"completed", "cancelled"}),
    "completed": frozenset({"in_progress"}),   # reopen (reason required)
    "cancelled": frozenset({"pending"}),       # restore (reason required)
}

# Transitions that must record a justification (mirrors task lifecycle rules).
STAGE_REASON_REQUIRED: frozenset[tuple[str, str]] = frozenset(
    {
        ("in_progress", "cancelled"),
        ("pending", "cancelled"),
        ("completed", "in_progress"),
        ("cancelled", "pending"),
    }
)

WORK_ITEM_REASON_REQUIRED: frozenset[tuple[str, str]] = frozenset(
    {
        ("in_progress", "cancelled"),
        ("pending", "cancelled"),
        ("completed", "in_progress"),
        ("cancelled", "pending"),
    }
)


def validate_stage_transition(
    current: str, target: str, *, reason: str | None = None
) -> str:
    current = _norm(current)
    target = _norm(target)
    if target not in STAGE_TRANSITIONS.get(current, frozenset()):
        raise WorkflowTransitionError(
            f"Transition of a stage from '{current}' to '{target}' is not allowed.",
            code="invalid_transition",
        )
    if (current, target) in STAGE_REASON_REQUIRED and not (reason and reason.strip()):
        raise WorkflowTransitionError(
            "A recorded reason is required for this stage transition.",
            code="reason_required",
        )
    return target


def validate_work_item_transition(
    current: str, target: str, *, reason: str | None = None
) -> str:
    current = _norm(current)
    target = _norm(target)
    if target not in WORK_ITEM_TRANSITIONS.get(current, frozenset()):
        raise WorkflowTransitionError(
            f"Transition of a work item from '{current}' to '{target}' is not allowed.",
            code="invalid_transition",
        )
    if (current, target) in WORK_ITEM_REASON_REQUIRED and not (reason and reason.strip()):
        raise WorkflowTransitionError(
            "A recorded reason is required for this work item transition.",
            code="reason_required",
        )
    return target


def _norm(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


# ---------------------------------------------------------------------------
# Dependency graph (within one task)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Edge:
    predecessor_id: uuid.UUID
    successor_id: uuid.UUID


def validate_dependency(
    edges: frozenset[Edge] | set[Edge],
    *,
    predecessor_id: uuid.UUID,
    successor_id: uuid.UUID,
) -> None:
    """Validate adding predecessor -> successor. Rejects self edges,
    duplicates and anything that would close a cycle (DFS reachability)."""
    if predecessor_id == successor_id:
        raise WorkflowTransitionError(
            "A work item cannot depend on itself.", code="self_dependency"
        )
    edge = Edge(predecessor_id=predecessor_id, successor_id=successor_id)
    if edge in set(edges):
        raise WorkflowTransitionError(
            "This dependency already exists.", code="duplicate_dependency"
        )
    if _reachable(set(edges), start=successor_id, goal=predecessor_id):
        raise WorkflowTransitionError(
            "This dependency would create a circular dependency chain, "
            "which is not allowed.",
            code="dependency_cycle",
        )


def has_cycle(edges: set[Edge] | frozenset[Edge]) -> bool:
    """True when the directed graph contains any cycle (used by tests and
    as a defensive full-graph check)."""
    nodes = {n for e in edges for n in (e.predecessor_id, e.successor_id)}
    edge_set = set(edges)
    for node in nodes:
        if node in _reachable_from(edge_set, node):
            return True
    return False


def _reachable_from(edges: set[Edge], start: uuid.UUID) -> set[uuid.UUID]:
    """All nodes reachable from `start` via one or more predecessor ->
    successor edges (the start node itself only counts if a cycle returns
    to it)."""
    adjacency: dict[uuid.UUID, list[uuid.UUID]] = {}
    for e in edges:
        adjacency.setdefault(e.predecessor_id, []).append(e.successor_id)
    seen: set[uuid.UUID] = set()
    frontier = [start]
    while frontier:
        node = frontier.pop()
        for nxt in adjacency.get(node, ()):  # DFS
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    return seen


def _reachable(edges: set[Edge], *, start: uuid.UUID, goal: uuid.UUID) -> bool:
    """Is `goal` reachable from `start` following predecessor -> successor?"""
    return goal in _reachable_from(edges, start)


def unmet_predecessors(
    edges: set[Edge] | frozenset[Edge],
    item_status: dict[uuid.UUID, str],
    item_id: uuid.UUID,
) -> list[uuid.UUID]:
    """Predecessors of `item_id` whose completion is still outstanding.

    Completed predecessors are satisfied; cancelled predecessors are treated
    as satisfied as well (the dependency is void once that scope is dropped -
    the cancellation itself is audited)."""
    unmet: list[uuid.UUID] = []
    for e in edges:
        if e.successor_id != item_id:
            continue
        status = _norm(item_status.get(e.predecessor_id, "pending"))
        if status not in {"completed", "cancelled"}:
            unmet.append(e.predecessor_id)
    return unmet


def blockers_for(edges: set[Edge] | frozenset[Edge], item_status: dict[uuid.UUID, str]) -> dict[uuid.UUID, list[uuid.UUID]]:
    """Map of item_id -> unmet predecessor ids, for the whole task."""
    result: dict[uuid.UUID, list[uuid.UUID]] = {}
    successors = {e.successor_id for e in edges}
    for successor in successors:
        unmet = unmet_predecessors(edges, item_status, successor)
        if unmet:
            result[successor] = unmet
    return result


def would_orphan_item(edges: set[Edge] | frozenset[Edge], item_id: uuid.UUID) -> bool:
    """True when other items still depend on `item_id` (guards deletes)."""
    return any(e.predecessor_id == item_id for e in edges)


# ---------------------------------------------------------------------------
# Sequential / parallel / mixed execution
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StageState:
    """The minimal stage facts the actionability rules need."""

    id: uuid.UUID
    sequence_number: int
    execution_mode: str  # "sequential" | "parallel"
    status: str


def stage_is_actionable(stages: list[StageState], stage_id: uuid.UUID) -> bool:
    """May `stage_id` start (move pending -> in_progress)?

    - parallel stages may start immediately (subject only to their own
      work items' dependencies - handled elsewhere),
    - sequential stages require every lower-numbered stage to be completed
      or cancelled,
    - already-started stages are trivially actionable."""
    by_id = {s.id: s for s in stages}
    stage = by_id.get(stage_id)
    if stage is None:
        raise WorkflowTransitionError("Unknown stage.", code="stage_not_found")
    if stage.status != "pending":
        return True
    if _norm(stage.execution_mode) == "parallel":
        return True
    for other in stages:
        if other.id == stage.id or other.sequence_number >= stage.sequence_number:
            continue
        if _norm(other.status) not in {"completed", "cancelled"}:
            return False
    return True


# ---------------------------------------------------------------------------
# Completion rules
# ---------------------------------------------------------------------------

@dataclass
class ItemFacts:
    """The minimal work-item facts the completion rules need."""

    id: uuid.UUID
    item_type: str          # "milestone" | "subtask"
    parent_id: uuid.UUID | None
    status: str
    is_required: bool
    weight: int = 1
    title: str = ""


def milestone_incomplete_subtasks(
    items: list[ItemFacts], milestone_id: uuid.UUID
) -> list[ItemFacts]:
    """Required, non-cancelled subtasks of a milestone that are not completed."""
    by_parent: dict[uuid.UUID, list[ItemFacts]] = {}
    for item in items:
        if item.parent_id is not None:
            by_parent.setdefault(item.parent_id, []).append(item)
    subtasks = by_parent.get(milestone_id, [])
    return [
        s for s in subtasks
        if s.is_required and _norm(s.status) not in {"completed", "cancelled"}
    ]


def item_may_complete(items: list[ItemFacts], item_id: uuid.UUID) -> None:
    """Completion requirements for a single work item.

    A milestone with outstanding required subtasks cannot be completed by
    hand - it auto-completes when its last required subtask completes
    (service layer). Raises WorkflowTransitionError otherwise."""
    item = next((i for i in items if i.id == item_id), None)
    if item is None:
        raise WorkflowTransitionError("Unknown work item.", code="item_not_found")
    if _norm(item.item_type) == "milestone":
        outstanding = milestone_incomplete_subtasks(items, item_id)
        if outstanding:
            raise WorkflowTransitionError(
                f"This milestone still has {len(outstanding)} incomplete required "
                "subtask(s); complete them first.",
                code="milestone_subtasks_incomplete",
            )


def stage_may_complete(items: list[ItemFacts], stage_item_ids: set[uuid.UUID]) -> None:
    """A stage can complete only when every required, non-cancelled work
    item in it is completed (optional and cancelled items never block;
    cancelled required items represent an audited scope decision)."""
    in_stage = [i for i in items if i.id in stage_item_ids]
    outstanding = [
        i for i in in_stage
        if i.is_required
        and _norm(i.status) not in {"completed", "cancelled"}
    ]
    if outstanding:
        titles = ", ".join(i.title or str(i.id) for i in outstanding[:3])
        raise WorkflowTransitionError(
            f"The stage still has {len(outstanding)} incomplete required work item(s): {titles}.",
            code="stage_items_incomplete",
        )
