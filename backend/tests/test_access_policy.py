"""Task access policy engine unit tests."""

import uuid

import pytest

from app.domain.access_policy import (
    ADMIN_BYPASS_PERMISSION,
    AccessDecision,
    AccessPolicy,
    ActorContext,
    Operation,
    VisibilityMode,
    evaluate_access,
    nested_resource_access,
    validate_policy,
)

ALICE = uuid.uuid4()
BOB = uuid.uuid4()
CAROL = uuid.uuid4()
DAVE = uuid.uuid4()
TASK = uuid.uuid4()
DEP_A = uuid.uuid4()
DEP_B = uuid.uuid4()

VIEW = Operation.VIEW
DEPARTMENT_VIEW_PERMISSIONS = {"tasks.view_department"}


def actor(
    user_id: uuid.UUID = BOB,
    permissions: set[str] | None = None,
    departments: set[uuid.UUID] | None = None,
    admin: bool = False,
) -> ActorContext:
    return ActorContext(
        user_id=user_id,
        permission_codes=frozenset(permissions or set()),
        department_ids=frozenset(departments or set()),
        is_privileged_admin=admin,
    )


def policy(mode: VisibilityMode, **kwargs) -> AccessPolicy:
    return AccessPolicy(task_id=TASK, mode=mode, **kwargs)


# ---------- structural validation ----------

class TestPolicyValidation:
    def test_valid_policies_produce_no_problems(self):
        assert validate_policy(policy(VisibilityMode.PRIVATE, participant_ids=frozenset({ALICE}))) == []
        assert validate_policy(policy(VisibilityMode.PARTICIPANTS, participant_ids=frozenset({ALICE}))) == []
        assert validate_policy(policy(VisibilityMode.DEPARTMENT_SCOPED, department_ids=frozenset({DEP_A}))) == []
        assert validate_policy(policy(VisibilityMode.CUSTOM, explicit_grants=frozenset({ALICE}))) == []

    def test_private_requires_participants(self):
        assert validate_policy(policy(VisibilityMode.PRIVATE))

    def test_department_scoped_requires_departments(self):
        assert validate_policy(policy(VisibilityMode.DEPARTMENT_SCOPED))

    def test_custom_requires_explicit_grants(self):
        assert validate_policy(policy(VisibilityMode.CUSTOM))

    def test_grant_and_denial_conflict_is_invalid(self):
        problems = validate_policy(
            policy(VisibilityMode.PARTICIPANTS,
                   participant_ids=frozenset({ALICE}),
                   explicit_grants=frozenset({BOB}),
                   explicit_denials=frozenset({BOB}))
        )
        assert any("both granted and denied" in p for p in problems)

    def test_mode_is_mandatory(self):
        with pytest.raises(ValueError):
            AccessPolicy(task_id=TASK, mode="private")  # type: ignore[arg-type]


# ---------- private mode ----------

class TestPrivate:
    def test_participant_can_view(self):
        p = policy(VisibilityMode.PRIVATE, participant_ids=frozenset({ALICE}), creator_id=CAROL)
        assert evaluate_access(actor(ALICE), p, VIEW) is AccessDecision.ALLOW

    def test_creator_can_view_and_update(self):
        p = policy(VisibilityMode.PRIVATE, participant_ids=frozenset(), creator_id=CAROL)
        assert evaluate_access(actor(CAROL), p, VIEW) is AccessDecision.ALLOW
        assert evaluate_access(actor(CAROL), p, Operation.UPDATE) is AccessDecision.ALLOW

    def test_outsider_cannot_view(self):
        p = policy(VisibilityMode.PRIVATE, participant_ids=frozenset({ALICE}), creator_id=CAROL)
        assert evaluate_access(actor(BOB), p, VIEW) is AccessDecision.DENY

    def test_department_membership_does_not_leak_into_private(self):
        # Even department members holding the department view permission
        # cannot see a private task they are not part of.
        p = policy(VisibilityMode.PRIVATE, participant_ids=frozenset({ALICE}))
        insider = actor(BOB, permissions=DEPARTMENT_VIEW_PERMISSIONS, departments={DEP_A})
        assert evaluate_access(insider, p, VIEW) is AccessDecision.DENY


# ---------- participants mode ----------

class TestParticipants:
    def test_participant_view_and_comment(self):
        p = policy(VisibilityMode.PARTICIPANTS, participant_ids=frozenset({ALICE}))
        a = actor(ALICE)
        assert evaluate_access(a, p, VIEW) is AccessDecision.ALLOW
        assert evaluate_access(a, p, Operation.COMMENT) is AccessDecision.ALLOW

    def test_participant_without_update_permission_cannot_restructure(self):
        p = policy(VisibilityMode.PARTICIPANTS, participant_ids=frozenset({ALICE}))
        assert evaluate_access(actor(ALICE), p, Operation.UPDATE) is AccessDecision.DENY
        assert evaluate_access(actor(ALICE), p, Operation.ASSIGN) is AccessDecision.DENY

    def test_participant_with_update_permission_can_update(self):
        p = policy(VisibilityMode.PARTICIPANTS, participant_ids=frozenset({ALICE}))
        assert evaluate_access(actor(ALICE, permissions={"tasks.update_assigned"}), p,
                               Operation.UPDATE) is AccessDecision.ALLOW

    def test_non_participant_denied(self):
        p = policy(VisibilityMode.PARTICIPANTS, participant_ids=frozenset({ALICE}))
        assert evaluate_access(actor(BOB, permissions={"tasks.update_assigned"}), p, VIEW) is AccessDecision.DENY


# ---------- department_scoped mode ----------

class TestDepartmentScoped:
    def test_department_member_with_permission_can_view(self):
        p = policy(VisibilityMode.DEPARTMENT_SCOPED, department_ids=frozenset({DEP_A}))
        member = actor(BOB, permissions={"tasks.view_department"}, departments={DEP_A})
        assert evaluate_access(member, p, VIEW) is AccessDecision.ALLOW

    def test_department_member_without_permission_cannot_view(self):
        p = policy(VisibilityMode.DEPARTMENT_SCOPED, department_ids=frozenset({DEP_A}))
        member = actor(BOB, departments={DEP_A})
        assert evaluate_access(member, p, VIEW) is AccessDecision.DENY

    def test_wrong_department_denied(self):
        p = policy(VisibilityMode.DEPARTMENT_SCOPED, department_ids=frozenset({DEP_A}))
        member = actor(BOB, permissions={"tasks.view_department"}, departments={DEP_B})
        assert evaluate_access(member, p, VIEW) is AccessDecision.DENY

    def test_direct_participant_can_view_even_without_department(self):
        p = policy(VisibilityMode.DEPARTMENT_SCOPED, participant_ids=frozenset({ALICE}),
                   department_ids=frozenset({DEP_A}))
        assert evaluate_access(actor(ALICE), p, VIEW) is AccessDecision.ALLOW


# ---------- custom mode ----------

class TestCustom:
    def test_granted_user_can_view(self):
        p = policy(VisibilityMode.CUSTOM, explicit_grants=frozenset({ALICE}))
        assert evaluate_access(actor(ALICE), p, VIEW) is AccessDecision.ALLOW

    def test_unguser_denied(self):
        p = policy(VisibilityMode.CUSTOM, explicit_grants=frozenset({ALICE}))
        assert evaluate_access(actor(BOB), p, VIEW) is AccessDecision.DENY


# ---------- precedence, admins, denials ----------

class TestPrecedence:
    def test_explicit_denial_beats_everything(self):
        p = policy(VisibilityMode.CUSTOM, explicit_grants=frozenset({ALICE}),
                   explicit_denials=frozenset({ALICE}))
        assert evaluate_access(actor(ALICE), p, VIEW) is AccessDecision.DENY

    def test_denial_beats_admin_bypass(self):
        p = policy(VisibilityMode.PARTICIPANTS, participant_ids=frozenset({ALICE}),
                   explicit_denials=frozenset({ADMIN_ID := uuid.uuid4()}))
        admin = actor(ADMIN_ID, permissions={ADMIN_BYPASS_PERMISSION}, admin=True)
        assert evaluate_access(admin, p, VIEW) is AccessDecision.DENY

    def test_permitted_admin_bypasses_scope(self):
        p = policy(VisibilityMode.PRIVATE, participant_ids=frozenset({ALICE}))
        admin = actor(DAVE, permissions={ADMIN_BYPASS_PERMISSION}, admin=True)
        assert evaluate_access(admin, p, VIEW) is AccessDecision.ALLOW
        assert evaluate_access(admin, p, Operation.UPDATE) is AccessDecision.ALLOW

    def test_admin_without_manage_all_permission_is_ordinary_user(self):
        p = policy(VisibilityMode.PRIVATE, participant_ids=frozenset({ALICE}))
        admin = actor(DAVE, permissions=set(), admin=True)
        assert evaluate_access(admin, p, VIEW) is AccessDecision.DENY

    def test_grant_beats_scope_limitations(self):
        # Bob is not a participant and holds no department rights, but has an
        # explicit grant on this task.
        p = policy(VisibilityMode.PARTICIPANTS, participant_ids=frozenset({ALICE}),
                   explicit_grants=frozenset({BOB}))
        assert evaluate_access(actor(BOB), p, VIEW) is AccessDecision.ALLOW
        assert evaluate_access(actor(BOB), p, Operation.COMMENT) is AccessDecision.ALLOW

    def test_change_visibility_requires_update_permission_even_for_granted(self):
        p = policy(VisibilityMode.CUSTOM, explicit_grants=frozenset({ALICE}))
        assert evaluate_access(actor(ALICE), p, Operation.CHANGE_VISIBILITY) is AccessDecision.DENY
        assert evaluate_access(
            actor(ALICE, permissions={"tasks.update_assigned"}), p, Operation.CHANGE_VISIBILITY
        ) is AccessDecision.ALLOW


class TestNestedResources:
    def test_nested_inherits_task_decision(self):
        p = policy(VisibilityMode.PARTICIPANTS, participant_ids=frozenset({ALICE}))
        assert nested_resource_access(actor(ALICE), p, Operation.COMMENT) is AccessDecision.ALLOW
        assert nested_resource_access(actor(BOB), p, Operation.COMMENT) is AccessDecision.DENY
