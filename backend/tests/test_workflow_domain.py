"""Phase 5 — Workflow Engine domain unit tests (pure logic).

Exit criteria coverage: "Invalid transitions and dependency cycles are
rejected", sequential/parallel/mixed actionability, completion rules and the
progress calculation (AC-04/05/06).
"""

import uuid

import pytest

from app.domain.progress import StageFacts, compute_progress, milestone_effectively_complete
from app.domain.workflow import (
    Edge,
    ItemFacts,
    StageState,
    WorkflowTransitionError,
    blockers_for,
    has_cycle,
    item_may_complete,
    milestone_incomplete_subtasks,
    stage_is_actionable,
    stage_may_complete,
    unmet_predecessors,
    validate_dependency,
    validate_stage_transition,
    validate_work_item_transition,
)


def uid() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Stage state machine
# ---------------------------------------------------------------------------

class TestStageStateMachine:
    def test_happy_path_pending_to_in_progress_to_completed(self):
        assert validate_stage_transition("pending", "in_progress") == "in_progress"
        assert validate_stage_transition("in_progress", "completed") == "completed"

    def test_invalid_transitions_rejected(self):
        with pytest.raises(WorkflowTransitionError):
            validate_stage_transition("pending", "completed")  # must start first
        with pytest.raises(WorkflowTransitionError):
            validate_stage_transition("completed", "cancelled")
        with pytest.raises(WorkflowTransitionError):
            validate_stage_transition("cancelled", "in_progress")
        with pytest.raises(WorkflowTransitionError):
            validate_stage_transition("pending", "pending")

    def test_reopen_and_restore_require_reason(self):
        with pytest.raises(WorkflowTransitionError) as exc:
            validate_stage_transition("completed", "in_progress")
        assert exc.value.code == "reason_required"
        assert validate_stage_transition("completed", "in_progress", reason="rework needed")

    def test_unknown_status_rejected(self):
        with pytest.raises(WorkflowTransitionError) as exc:
            validate_stage_transition("pending", "archived")
        assert exc.value.code == "invalid_transition"


class TestWorkItemStateMachine:
    def test_happy_path(self):
        assert validate_work_item_transition("pending", "in_progress")
        assert validate_work_item_transition("in_progress", "completed")

    def test_invalid_transitions_rejected(self):
        with pytest.raises(WorkflowTransitionError):
            validate_work_item_transition("pending", "completed")
        with pytest.raises(WorkflowTransitionError):
            validate_work_item_transition("cancelled", "completed")

    def test_cancel_requires_reason(self):
        with pytest.raises(WorkflowTransitionError) as exc:
            validate_work_item_transition("in_progress", "cancelled")
        assert exc.value.code == "reason_required"


# ---------------------------------------------------------------------------
# Dependency graph
# ---------------------------------------------------------------------------

class TestDependencyGraph:
    def test_self_dependency_rejected(self):
        item = uid()
        with pytest.raises(WorkflowTransitionError) as exc:
            validate_dependency(set(), predecessor_id=item, successor_id=item)
        assert exc.value.code == "self_dependency"

    def test_duplicate_dependency_rejected(self):
        a, b = uid(), uid()
        edges = {Edge(predecessor_id=a, successor_id=b)}
        with pytest.raises(WorkflowTransitionError) as exc:
            validate_dependency(edges, predecessor_id=a, successor_id=b)
        assert exc.value.code == "duplicate_dependency"

    def test_direct_cycle_rejected(self):
        a, b = uid(), uid()
        edges = {Edge(predecessor_id=a, successor_id=b)}
        with pytest.raises(WorkflowTransitionError) as exc:
            validate_dependency(edges, predecessor_id=b, successor_id=a)
        assert exc.value.code == "dependency_cycle"

    def test_transitive_cycle_rejected(self):
        a, b, c = uid(), uid(), uid()
        edges = {
            Edge(predecessor_id=a, successor_id=b),
            Edge(predecessor_id=b, successor_id=c),
        }
        # a -> b -> c: adding c -> a closes the loop across three items.
        with pytest.raises(WorkflowTransitionError) as exc:
            validate_dependency(edges, predecessor_id=c, successor_id=a)
        assert exc.value.code == "dependency_cycle"

    def test_diamond_is_not_a_cycle(self):
        a, b, c, d = uid(), uid(), uid(), uid()
        edges = {
            Edge(predecessor_id=a, successor_id=b),
            Edge(predecessor_id=a, successor_id=c),
            Edge(predecessor_id=b, successor_id=d),
            Edge(predecessor_id=c, successor_id=d),
        }
        assert not has_cycle(edges)
        # A shared predecessor with converging successors stays acyclic.
        validate_dependency(edges, predecessor_id=a, successor_id=d)  # duplicate? no: a->d is new

    def test_long_chain_through_stages_is_detected(self):
        ids = [uid() for _ in range(6)]
        edges = {Edge(predecessor_id=ids[i], successor_id=ids[i + 1]) for i in range(5)}
        with pytest.raises(WorkflowTransitionError):
            validate_dependency(edges, predecessor_id=ids[5], successor_id=ids[0])

    def test_has_cycle_full_graph(self):
        a, b = uid(), uid()
        assert has_cycle({Edge(a, b), Edge(b, a)})
        assert not has_cycle({Edge(a, b)})

    def test_unmet_predecessors(self):
        a, b = uid(), uid()
        edges = {Edge(predecessor_id=a, successor_id=b)}
        statuses = {a: "in_progress", b: "pending"}
        assert unmet_predecessors(edges, statuses, b) == [a]
        statuses[a] = "completed"
        assert unmet_predecessors(edges, statuses, b) == []
        statuses[a] = "cancelled"  # cancelled predecessor satisfies the edge
        assert unmet_predecessors(edges, statuses, b) == []

    def test_blockers_for_maps_only_blocked_items(self):
        a, b, c = uid(), uid(), uid()
        edges = {Edge(a, b), Edge(a, c)}
        statuses = {a: "pending", b: "pending", c: "in_progress"}
        blockers = blockers_for(edges, statuses)
        assert set(blockers) == {b, c}
        assert blockers[b] == [a]

    def test_would_orphan_item(self):
        a, b = uid(), uid()
        edges = {Edge(a, b)}
        assert not hasattr(edges, "count")
        from app.domain.workflow import would_orphan_item
        assert would_orphan_item(edges, a)
        assert not would_orphan_item(edges, b)


# ---------------------------------------------------------------------------
# Sequential / parallel / mixed execution
# ---------------------------------------------------------------------------

def stage(sid, seq, mode, status):
    return StageState(id=sid, sequence_number=seq, execution_mode=mode, status=status)


class TestActionability:
    def test_first_sequential_stage_always_actionable(self):
        a = uid()
        assert stage_is_actionable([stage(a, 1, "sequential", "pending")], a)

    def test_sequential_gates_on_all_earlier_stages(self):
        a, b, c = uid(), uid(), uid()
        stages = [
            stage(a, 1, "sequential", "in_progress"),
            stage(b, 2, "sequential", "pending"),
            stage(c, 3, "sequential", "pending"),
        ]
        assert not stage_is_actionable(stages, b)
        assert not stage_is_actionable(stages, c)
        after = [
            stage(a, 1, "sequential", "completed"),
            stage(b, 2, "sequential", "pending"),
            stage(c, 3, "sequential", "pending"),
        ]
        assert stage_is_actionable(after, b)

    def test_cancelled_earlier_stage_satisfies_gate(self):
        a, b = uid(), uid()
        stages = [stage(a, 1, "sequential", "cancelled"), stage(b, 2, "sequential", "pending")]
        assert stage_is_actionable(stages, b)

    def test_parallel_stage_ignores_predecessors(self):
        a, b = uid(), uid()
        stages = [stage(a, 1, "sequential", "in_progress"), stage(b, 2, "parallel", "pending")]
        assert stage_is_actionable(stages, b)

    def test_mixed_workflow_combination(self):
        a, b, c, d = uid(), uid(), uid(), uid()
        stages = [
            stage(a, 1, "sequential", "pending"),
            stage(b, 2, "parallel", "pending"),
            stage(c, 3, "parallel", "pending"),
            stage(d, 4, "sequential", "pending"),
        ]
        assert stage_is_actionable(stages, a)
        assert not stage_is_actionable(stages, d)  # waits for 1-3

    def test_unknown_stage_raises(self):
        with pytest.raises(WorkflowTransitionError):
            stage_is_actionable([], uid())


# ---------------------------------------------------------------------------
# Completion rules
# ---------------------------------------------------------------------------

def item(iid, itype, status, *, parent=None, required=True, weight=1, title=""):
    return ItemFacts(id=iid, item_type=itype, parent_id=parent, status=status,
                     is_required=required, weight=weight, title=title or str(iid))


class TestCompletionRules:
    def test_milestone_with_open_required_subtasks_cannot_complete(self):
        m, s1, s2 = uid(), uid(), uid()
        items = [
            item(m, "milestone", "in_progress"),
            item(s1, "subtask", "completed", parent=m),
            item(s2, "subtask", "in_progress", parent=m),
        ]
        with pytest.raises(WorkflowTransitionError) as exc:
            item_may_complete(items, m)
        assert exc.value.code == "milestone_subtasks_incomplete"

    def test_milestone_completes_when_all_required_subtasks_done(self):
        m, s1, s2 = uid(), uid(), uid()
        items = [
            item(m, "milestone", "in_progress"),
            item(s1, "subtask", "completed", parent=m),
            item(s2, "subtask", "completed", parent=m),
        ]
        item_may_complete(items, m)  # no raise

    def test_optional_subtasks_do_not_block_milestone(self):
        m, s1, s2 = uid(), uid(), uid()
        items = [
            item(m, "milestone", "in_progress"),
            item(s1, "subtask", "completed", parent=m),
            item(s2, "subtask", "pending", parent=m, required=False),
        ]
        item_may_complete(items, m)
        assert milestone_incomplete_subtasks(items, m) == []

    def test_stage_completion_requires_all_required_items(self):
        i1, i2, i3 = uid(), uid(), uid()
        items = [
            item(i1, "milestone", "completed"),
            item(i2, "subtask", "in_progress"),
            item(i3, "subtask", "pending", required=False),
        ]
        with pytest.raises(WorkflowTransitionError) as exc:
            stage_may_complete(items, {i1, i2, i3})
        assert exc.value.code == "stage_items_incomplete"
        # cancelled required items are an audited scope decision, not a blocker
        items[1].status = "cancelled"
        stage_may_complete(items, {i1, i2, i3})


# ---------------------------------------------------------------------------
# Progress calculation (AC-06)
# ---------------------------------------------------------------------------

class TestProgressCalculation:
    def test_empty_workflow_is_zero(self):
        progress = compute_progress([], [])
        assert progress.task_percent == 0

    def test_weighted_stage_average(self):
        s1, s2 = uid(), uid()
        i1 = uid()
        stages = [
            StageFacts(id=str(s1), name="A", sequence_number=1, status="completed",
                       weight=1, progress_basis="all_items", item_ids=frozenset({str(i1)})),
            StageFacts(id=str(s2), name="B", sequence_number=2, status="in_progress",
                       weight=3, progress_basis="all_items", item_ids=frozenset()),
        ]
        items = [item(i1, "subtask", "completed")]
        progress = compute_progress(stages, items)
        # Stage A: 100% (weight 1); Stage B: 0% (weight 3) -> 100/4 = 25
        assert progress.task_percent == 25

    def test_item_weights_drive_stage_progress(self):
        s1 = uid()
        i1, i2 = uid(), uid()
        stages = [StageFacts(id=str(s1), name="A", sequence_number=1, status="in_progress",
                             weight=1, progress_basis="all_items",
                             item_ids=frozenset({str(i1), str(i2)}))]
        items = [item(i1, "subtask", "completed", weight=3),
                 item(i2, "subtask", "pending", weight=1)]
        progress = compute_progress(stages, items)
        assert progress.task_percent == 75

    def test_optional_and_cancelled_items_excluded(self):
        s1 = uid()
        i1, i2, i3 = uid(), uid(), uid()
        stages = [StageFacts(id=str(s1), name="A", sequence_number=1, status="in_progress",
                             weight=1, progress_basis="all_items",
                             item_ids=frozenset({str(i1), str(i2), str(i3)}))]
        items = [
            item(i1, "subtask", "completed"),
            item(i2, "subtask", "pending", required=False),
            item(i3, "subtask", "cancelled"),
        ]
        progress = compute_progress(stages, items)
        assert progress.task_percent == 100
        assert progress.stages[0].excluded.get("optional") == 1
        assert progress.stages[0].excluded.get("cancelled") == 1

    def test_subtasks_roll_into_milestone_no_double_counting(self):
        s1 = uid()
        m, s1a, s1b = uid(), uid(), uid()
        stages = [StageFacts(id=str(s1), name="A", sequence_number=1, status="in_progress",
                             weight=1, progress_basis="all_items",
                             item_ids=frozenset({str(m), str(s1a), str(s1b)}))]
        items = [
            item(m, "milestone", "in_progress", weight=5),
            item(s1a, "subtask", "completed", parent=m, weight=9),
            item(s1b, "subtask", "pending", parent=m, weight=9),
        ]
        progress = compute_progress(stages, items)
        # Only the milestone counts (weight 5, not complete) -> 0%, and the
        # subtasks (weights 9+9) are NOT added on top (no double counting).
        assert progress.task_percent == 0
        assert progress.stages[0].total_weight == 5
        # When subtasks finish, the milestone completes at its own weight.
        items[1].status = "completed"
        items[2].status = "completed"
        progress = compute_progress(stages, items)
        assert progress.task_percent == 100
        assert progress.stages[0].total_weight == 5

    def test_cancelled_stage_excluded_from_task_progress(self):
        s1, s2 = uid(), uid()
        stages = [
            StageFacts(id=str(s1), name="A", sequence_number=1, status="cancelled",
                       weight=5, progress_basis="all_items", item_ids=frozenset()),
            StageFacts(id=str(s2), name="B", sequence_number=2, status="in_progress",
                       weight=1, progress_basis="all_items", item_ids=frozenset()),
        ]
        progress = compute_progress(stages, [])
        assert progress.task_percent == 0
        assert progress.stages[0].excluded.get("stage_cancelled") == 1

    def test_completed_stage_counts_full_weight(self):
        s1 = uid()
        stages = [StageFacts(id=str(s1), name="A", sequence_number=1, status="completed",
                             weight=2, progress_basis="all_items", item_ids=frozenset())]
        progress = compute_progress(stages, [])
        assert progress.task_percent == 100

    def test_progress_basis_filters_item_types(self):
        s1 = uid()
        m, sub = uid(), uid()
        stages = [StageFacts(id=str(s1), name="A", sequence_number=1, status="in_progress",
                             weight=1, progress_basis="milestones_only",
                             item_ids=frozenset({str(m), str(sub)}))]
        items = [
            item(m, "milestone", "pending"),
            item(sub, "subtask", "completed"),
        ]
        progress = compute_progress(stages, items)
        assert progress.task_percent == 0  # the subtask is outside the basis
        assert progress.stages[0].excluded.get("basis_milestones_only") == 1

    def test_method_text_is_human_readable(self):
        s1 = uid()
        i1 = uid()
        stages = [StageFacts(id=str(s1), name="A", sequence_number=1, status="in_progress",
                             weight=1, progress_basis="all_items", item_ids=frozenset({str(i1)}))]
        items = [item(i1, "subtask", "completed")]
        progress = compute_progress(stages, items)
        assert "weighted" in progress.method.lower()
        assert progress.stages[0].method  # per-stage method present

    def test_milestone_effectively_complete_helper(self):
        m, sub = uid(), uid()
        items = [item(m, "milestone", "in_progress"),
                 item(sub, "subtask", "completed", parent=m)]
        assert milestone_effectively_complete(items, items[0])
        items[1].status = "pending"
        assert not milestone_effectively_complete(items, items[0])
