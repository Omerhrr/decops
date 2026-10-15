"""Task lifecycle state machine unit tests (spec testing_strategy.unit_tests:
"Task status transitions")."""

import pytest

from app.domain.task_lifecycle import (
    ALLOWED_TRANSITIONS,
    TaskStatus,
    TransitionError,
    validate_transition,
)


class TestAllowedTransitions:
    @pytest.mark.parametrize(
        ("current", "target"),
        [
            ("draft", "open"),
            ("open", "in_progress"),
            ("open", "blocked"),
            ("in_progress", "under_review"),
            ("in_progress", "completed"),
            ("in_progress", "blocked"),
            ("blocked", "in_progress"),
            ("under_review", "completed"),
            ("under_review", "in_progress"),
            ("completed", "in_progress"),  # reopen
            ("completed", "archived"),
            ("cancelled", "open"),  # reopen cancelled
            ("cancelled", "archived"),
        ],
    )
    def test_allowed(self, current, target):
        assert validate_transition(current, target, reason="because") == TaskStatus(target)

    @pytest.mark.parametrize(
        ("current", "target"),
        [
            ("draft", "completed"),
            ("draft", "archived"),
            ("open", "completed"),
            ("open", "under_review"),
            ("open", "archived"),
            ("blocked", "completed"),
            ("blocked", "under_review"),
            ("completed", "completed"),
            ("completed", "open"),
            ("completed", "cancelled"),
            ("cancelled", "completed"),
            ("archived", "open"),
            ("archived", "in_progress"),
        ],
    )
    def test_rejected(self, current, target):
        with pytest.raises(TransitionError) as exc:
            validate_transition(current, target)
        assert exc.value.code == "invalid_transition"

    def test_unknown_status_raises_machine_readable_error(self):
        with pytest.raises(TransitionError) as exc:
            validate_transition("archived", "not-a-status")
        assert exc.value.code == "invalid_status"

    def test_archived_is_terminal(self):
        assert ALLOWED_TRANSITIONS[TaskStatus.archived] == frozenset()


class TestReasonRequirements:
    def test_reopen_completed_requires_reason(self):
        with pytest.raises(TransitionError) as exc:
            validate_transition("completed", "in_progress", reason=None)
        assert exc.value.code == "reason_required"

    def test_reopen_completed_with_blank_reason_rejected(self):
        with pytest.raises(TransitionError) as exc:
            validate_transition("completed", "in_progress", reason="   ")
        assert exc.value.code == "reason_required"

    def test_cancel_requires_reason(self):
        with pytest.raises(TransitionError):
            validate_transition("in_progress", "cancelled", reason=None)

    def test_block_requires_explanation(self):
        with pytest.raises(TransitionError) as exc:
            validate_transition("open", "blocked", reason=None)
        assert exc.value.code == "blocker_explanation_required"

    def test_block_with_explanation_ok(self):
        assert (
            validate_transition("open", "blocked", reason="Waiting on vendor license") is not None
        )

    def test_normal_transition_without_reason_ok(self):
        assert validate_transition("open", "in_progress") == TaskStatus.in_progress
