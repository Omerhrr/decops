"""Assignment authorization tests
: one accountable PM, recorded assigning user)."""

import uuid

from app.domain.assignment_policy import (
    ACTOR_PERMISSIONS,
    AssignmentContext,
    AssignmentDeniedError,
    AssignmentRole,
    AssigneeProfile,
    replace_accountable_pm,
    validate_assignment,
)

ACTOR = uuid.uuid4()
PM_A = uuid.uuid4()
PM_B = uuid.uuid4()
OUTSIDER = uuid.uuid4()
TASK = uuid.uuid4()
DEP_A = uuid.uuid4()

TASK_DEPS = frozenset({DEP_A})
ASSIGN_PERMS = frozenset(ACTOR_PERMISSIONS[AssignmentRole.ACCOUNTABLE_PM])


def profile(user_id: uuid.UUID, *, status: str = "active", departments: frozenset = TASK_DEPS) -> AssigneeProfile:
    return AssigneeProfile(
        user_id=user_id,
        account_status=status,
        permission_codes=frozenset(),
        department_ids=departments,
    )


def context(**kwargs) -> AssignmentContext:
    defaults = dict(task_id=TASK, task_department_ids=TASK_DEPS)
    defaults.update(kwargs)
    return AssignmentContext(**defaults)


class TestActorAuthorization:
    def test_actor_without_permission_cannot_assign_accountable_pm(self):
        try:
            validate_assignment(ACTOR, frozenset(), AssignmentRole.ACCOUNTABLE_PM,
                                profile(PM_A), context())
            raise AssertionError("expected AssignmentDeniedError")
        except AssignmentDeniedError as exc:
            assert "lacks the permission" in exc.reason

    def test_actor_with_permission_can_assign(self):
        assigning_user = validate_assignment(
            ACTOR, ASSIGN_PERMS, AssignmentRole.ACCOUNTABLE_PM, profile(PM_A), context()
        )
        # The assigning user is recorded.
        assert assigning_user == str(ACTOR)


class TestAssigneeValidation:
    def test_deactivated_employee_cannot_be_assigned(self):
        for status in ("disabled", "deactivated"):
            try:
                validate_assignment(ACTOR, ASSIGN_PERMS, AssignmentRole.ACCOUNTABLE_PM,
                                    profile(PM_A, status=status), context())
                raise AssertionError(f"expected denial for status={status}")
            except AssignmentDeniedError as exc:
                assert "not active" in exc.reason

    def test_assignee_must_belong_to_task_department(self):
        outsider_profile = profile(OUTSIDER, departments=frozenset({uuid.uuid4()}))
        try:
            validate_assignment(ACTOR, ASSIGN_PERMS, AssignmentRole.SUPPORTING_PM,
                                outsider_profile, context())
            raise AssertionError("expected AssignmentDeniedError")
        except AssignmentDeniedError as exc:
            assert "department" in exc.reason


class TestAccountablePmRules:
    def test_replacement_changes_the_single_pm(self):
        ctx = context(current_accountable_pm=PM_A)
        updated = replace_accountable_pm(ctx, PM_B)
        assert updated.current_accountable_pm == PM_B

    def test_new_pm_is_removed_from_supporting_list(self):
        ctx = context(current_accountable_pm=PM_A, current_supporting_pms=frozenset({PM_B}))
        updated = replace_accountable_pm(ctx, PM_B)
        assert PM_B not in updated.current_supporting_pms

    def test_idempotent_reassignment_returns_actor_for_audit(self):
        ctx = context(current_accountable_pm=PM_A)
        recorded = validate_assignment(ACTOR, ASSIGN_PERMS, AssignmentRole.ACCOUNTABLE_PM,
                                       profile(PM_A), ctx)
        assert recorded == str(ACTOR)


class TestWorkItemAssignment:
    def test_work_item_role_needs_work_item_permission(self):
        # tasks.assign_department alone does NOT authorize work-item assignment
        # (the work-item matrix needs work_items.update_assigned or tasks.update_assigned).
        try:
            validate_assignment(ACTOR, frozenset({"tasks.assign_department"}),
                                AssignmentRole.WORK_ITEM_ASSIGNEE, profile(PM_A), context())
            raise AssertionError("expected denial")
        except AssignmentDeniedError:
            pass
        # tasks.update_assigned also allows work item assignment (fallback permission)
        recorded = validate_assignment(
            ACTOR, frozenset({"tasks.update_assigned"}), AssignmentRole.WORK_ITEM_ASSIGNEE,
            profile(PM_A), context(),
        )
        assert recorded == str(ACTOR)
