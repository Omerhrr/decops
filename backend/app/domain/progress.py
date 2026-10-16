"""Workflow progress calculation.

Pure functions over plain facts so the calculation is exhaustively unit
testable and independently displayable ("Display the calculation method to
authorized users" - the breakdown returned here is exactly what the API
shows).

Rules (each maps to a):

- Default: progress comes from required work items and configured stage
  weights ("Calculate progress from required work items and configured
  stage weights").
- Optional (is_required=False) items contribute nothing.
- Cancelled items are excluded; cancelled stages are excluded entirely.
- A milestone that has required subtasks counts ONCE, with its completion
  derived from those subtasks - its subtasks are never also counted, so the
  same work is not double-counted ("Avoid counting the same work twice").
- Item completion is binary (completed contributes its weight; anything
  else contributes 0) - no invented fractions ("Distinguish calculated
  progress from manually entered progress": manual percent on the task is a
  separate mode; the engine never fabricates partial credit).
- Every stage reports the counting method it used alongside its numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.workflow import ItemFacts


@dataclass(frozen=True)
class StageFacts:
    """The minimal stage facts the engine needs (mirrors TaskStage)."""

    id: str
    name: str
    sequence_number: int
    status: str                      # pending/in_progress/completed/cancelled
    weight: int
    progress_basis: str              # all_items/milestones_only/subtasks_only
    item_ids: frozenset[str] = field(default_factory=frozenset)


@dataclass
class StageProgressBreakdown:
    stage_id: str
    stage_name: str
    status: str
    weight: int
    included_item_count: int = 0
    completed_item_count: int = 0
    total_weight: int = 0
    completed_weight: int = 0
    percent: int = 0
    excluded: dict[str, int] = field(default_factory=dict)  # reason -> count
    method: str = ""


@dataclass
class WorkflowProgress:
    task_percent: int = 0
    stages: list[StageProgressBreakdown] = field(default_factory=list)
    method: str = (
        "Weighted average of non-cancelled stages; each stage is the weighted "
        "share of its required, non-cancelled work items that have completed. "
        "Optional and cancelled items are excluded, and subtasks roll up into "
        "their milestone instead of being counted twice."
    )
    counted_item_total: int = 0
    counted_item_completed: int = 0


def _norm(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def milestone_effectively_complete(items: list[ItemFacts], milestone: ItemFacts) -> bool:
    """A milestone with required subtasks is complete only when all of those
    subtasks are completed (cancelled subtasks are excluded as an audited
    scope decision); a milestone without required subtasks uses its own
    status."""
    required_subtasks = [
        i for i in items
        if i.parent_id == milestone.id and i.is_required and _norm(i.status) != "cancelled"
    ]
    if not required_subtasks:
        return _norm(milestone.status) == "completed"
    return all(_norm(s.status) == "completed" for s in required_subtasks)


def _basis_accepts(basis: str, item_type: str) -> bool:
    if basis == "milestones_only":
        return item_type == "milestone"
    if basis == "subtasks_only":
        return item_type == "subtask"
    return True


def compute_progress(
    stages: list[StageFacts], items: list[ItemFacts]
) -> WorkflowProgress:
    """Calculate task progress from stages and work items.

    `items` must contain every work item of the task (all stages, all
    nesting levels) so milestone roll-up can avoid double counting.
    """
    items_by_id = {i.id: i for i in items}
    breakdowns: list[StageProgressBreakdown] = []
    total_weight = 0
    weighted_sum = 0.0
    counted_total = 0
    counted_completed = 0

    for stage in sorted(stages, key=lambda s: s.sequence_number):
        status = _norm(stage.status)
        if status == "cancelled":
            breakdown = StageProgressBreakdown(
                stage_id=str(stage.id), stage_name=stage.name, status=status,
                weight=stage.weight,
            )
            breakdown.excluded["stage_cancelled"] = 1
            breakdown.method = "Stage cancelled - excluded from task progress."
            breakdowns.append(breakdown)
            continue

        # Top-level items of this stage (subtasks roll into milestones).
        top_level = [
            i for i in items
            if str(i.id) in {str(sid) for sid in stage.item_ids} and i.parent_id is None
        ]
        breakdown = StageProgressBreakdown(
            stage_id=str(stage.id), stage_name=stage.name, status=status,
            weight=stage.weight,
        )

        counted: list[tuple[ItemFacts, bool, int]] = []  # (item, effectively_complete, weight)
        for item in top_level:
            item_type = _norm(item.item_type)
            if not item.is_required:
                breakdown.excluded["optional"] = breakdown.excluded.get("optional", 0) + 1
                continue
            if _norm(item.status) == "cancelled":
                breakdown.excluded["cancelled"] = breakdown.excluded.get("cancelled", 0) + 1
                continue
            if not _basis_accepts(_norm(stage.progress_basis), item_type):
                breakdown.excluded[f"basis_{_norm(stage.progress_basis)}"] = (
                    breakdown.excluded.get(f"basis_{_norm(stage.progress_basis)}", 0) + 1
                )
                continue
            complete = (
                milestone_effectively_complete(items, item)
                if item_type == "milestone"
                else _norm(item.status) == "completed"
            )
            counted.append((item, complete, max(1, int(item.weight or 1))))

        breakdown.included_item_count = len(counted)
        breakdown.total_weight = sum(w for _, _, w in counted)
        breakdown.completed_weight = sum(w for _, complete, w in counted if complete)
        breakdown.completed_item_count = sum(1 for _, complete, _ in counted if complete)
        counted_total += breakdown.included_item_count
        counted_completed += breakdown.completed_item_count

        if status == "completed":
            # A manually completed stage with no counting items is 100%.
            breakdown.percent = 100
            breakdown.method = (
                "Stage is completed; contributes its full stage weight to the task."
            )
        elif breakdown.total_weight > 0:
            breakdown.percent = round(breakdown.completed_weight * 100 / breakdown.total_weight)
            breakdown.method = (
                f"{breakdown.completed_weight} of {breakdown.total_weight} weighted "
                f"required item(s) completed ({breakdown.completed_item_count} of "
                f"{breakdown.included_item_count} items)."
            )
        else:
            breakdown.percent = 0
            breakdown.method = (
                "No required work items configured; stage contributes 0% until "
                "items are added or the stage is completed."
            )

        total_weight += stage.weight
        weighted_sum += stage.weight * breakdown.percent
        breakdowns.append(breakdown)

    task_percent = round(weighted_sum / total_weight) if total_weight > 0 else 0
    return WorkflowProgress(
        task_percent=max(0, min(100, task_percent)),
        stages=breakdowns,
        counted_item_total=counted_total,
        counted_item_completed=counted_completed,
    )
