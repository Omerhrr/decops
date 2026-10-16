"""Cross-task isolation tests (exit criterion: "Cross-task isolation
tests pass") plus immediate-revocation guarantees at both the domain and API
layer. These tests are the safety net the before task CRUD
arrives."""

import uuid

from fastapi.testclient import TestClient

from app.domain.access_policy import (
    AccessDecision,
    AccessPolicy,
    ActorContext,
    Operation,
    VisibilityMode,
    evaluate_access,
    require_access,
)
from app.domain.access_policy import AccessDeniedError

from tests.conftest import login, make_user

ALICE_EMAIL = "alice.isolation@interdec.com"
BOB_EMAIL = "bob.isolation@interdec.com"


def actor_ctx(user_id: uuid.UUID, *, permissions: set[str] | None = None,
              departments: set[uuid.UUID] | None = None) -> ActorContext:
    return ActorContext(
        user_id=user_id,
        permission_codes=frozenset(permissions or set()),
        department_ids=frozenset(departments or set()),
    )


class TestCrossTaskIsolation:
    """Access to one task must never authorize access to an unrelated task."""

    def test_grant_on_task_a_does_not_leak_into_task_b(self):
        task_a, task_b = uuid.uuid4(), uuid.uuid4()
        alice = uuid.uuid4()

        policy_a = AccessPolicy(task_id=task_a, mode=VisibilityMode.CUSTOM,
                                explicit_grants=frozenset({alice}))
        policy_b = AccessPolicy(task_id=task_b, mode=VisibilityMode.PRIVATE)

        assert evaluate_access(actor_ctx(alice), policy_a, Operation.VIEW) is AccessDecision.ALLOW
        # The same actor, evaluated against task B, is an outsider: grants are
        # embedded per-policy and cannot leak across tasks.
        assert evaluate_access(actor_ctx(alice), policy_b, Operation.VIEW) is AccessDecision.DENY

    def test_participants_on_one_task_are_not_participants_on_another(self):
        task_a, task_b = uuid.uuid4(), uuid.uuid4()
        alice = uuid.uuid4()

        policy_a = AccessPolicy(task_id=task_a, mode=VisibilityMode.PARTICIPANTS,
                                participant_ids=frozenset({alice}))
        policy_b = AccessPolicy(task_id=task_b, mode=VisibilityMode.PARTICIPANTS,
                                participant_ids=frozenset())

        assert evaluate_access(actor_ctx(alice), policy_a, Operation.VIEW) is AccessDecision.ALLOW
        assert evaluate_access(actor_ctx(alice), policy_b, Operation.VIEW) is AccessDecision.DENY

    def test_department_access_to_task_a_does_not_cover_private_task_b(self):
        dep = uuid.uuid4()
        task_b = uuid.uuid4()
        member = uuid.uuid4()

        department_task = AccessPolicy(task_id=uuid.uuid4(), mode=VisibilityMode.DEPARTMENT_SCOPED,
                                       department_ids=frozenset({dep}))
        private_task = AccessPolicy(task_id=task_b, mode=VisibilityMode.PRIVATE)

        member_ctx = actor_ctx(member, permissions={"tasks.view_department"}, departments={dep})
        assert evaluate_access(member_ctx, department_task, Operation.VIEW) is AccessDecision.ALLOW
        assert evaluate_access(member_ctx, private_task, Operation.VIEW) is AccessDecision.DENY

    def test_viewing_a_task_does_not_authorize_every_operation_on_it(self):
        task = uuid.uuid4()
        viewer = uuid.uuid4()
        policy = AccessPolicy(task_id=task, mode=VisibilityMode.PARTICIPANTS,
                              participant_ids=frozenset({viewer}))
        ctx = actor_ctx(viewer)
        assert evaluate_access(ctx, policy, Operation.VIEW) is AccessDecision.ALLOW
        assert evaluate_access(ctx, policy, Operation.UPDATE) is AccessDecision.DENY
        assert evaluate_access(ctx, policy, Operation.ASSIGN) is AccessDecision.DENY

    def test_require_access_raises_with_task_identity(self):
        task = uuid.uuid4()
        policy = AccessPolicy(task_id=task, mode=VisibilityMode.PRIVATE)
        try:
            require_access(actor_ctx(uuid.uuid4()), policy, Operation.VIEW)
            raise AssertionError("expected AccessDeniedError")
        except AccessDeniedError as exc:
            assert exc.task_id == task
            assert exc.operation is Operation.VIEW


class TestPermissionRevocationIsImmediate:
    """Revoked access must take effect immediately for subsequent checks."""

    def test_role_loss_changes_the_next_decision(self):
        member = uuid.uuid4()
        dep = uuid.uuid4()
        policy = AccessPolicy(task_id=uuid.uuid4(), mode=VisibilityMode.DEPARTMENT_SCOPED,
                              department_ids=frozenset({dep}))

        with_permission = actor_ctx(member, permissions={"tasks.view_department"}, departments={dep})
        after_revocation = actor_ctx(member, permissions=set(), departments={dep})

        assert evaluate_access(with_permission, policy, Operation.VIEW) is AccessDecision.ALLOW
        assert evaluate_access(after_revocation, policy, Operation.VIEW) is AccessDecision.DENY

    def test_membership_loss_changes_the_next_decision(self):
        member = uuid.uuid4()
        dep = uuid.uuid4()
        policy = AccessPolicy(task_id=uuid.uuid4(), mode=VisibilityMode.DEPARTMENT_SCOPED,
                              department_ids=frozenset({dep}))
        assert evaluate_access(
            actor_ctx(member, permissions={"tasks.view_department"}, departments={dep}),
            policy, Operation.VIEW,
        ) is AccessDecision.ALLOW
        # Department membership removed -> next evaluation denies, even with
        # the permission still attached.
        assert evaluate_access(
            actor_ctx(member, permissions={"tasks.view_department"}, departments=set()),
            policy, Operation.VIEW,
        ) is AccessDecision.DENY

    def test_explicit_denial_takes_effect_over_existing_grant(self):
        user = uuid.uuid4()
        policy = AccessPolicy(task_id=uuid.uuid4(), mode=VisibilityMode.CUSTOM,
                              explicit_grants=frozenset({user}))
        assert evaluate_access(actor_ctx(user), policy, Operation.VIEW) is AccessDecision.ALLOW
        denied_policy = AccessPolicy(task_id=policy.task_id, mode=VisibilityMode.CUSTOM,
                                     explicit_grants=frozenset({user}),
                                     explicit_denials=frozenset({user}))
        assert evaluate_access(actor_ctx(user), denied_policy, Operation.VIEW) is AccessDecision.DENY


class TestDeactivationEndsApiAccessImmediately:
    """A deactivated employee's session stops working on the very next request."""

    def test_deactivated_user_cannot_use_existing_session(self, client: TestClient, test_db):
        from fastapi.testclient import TestClient as TC

        from app.main import create_app

        alice = make_user(test_db, email=ALICE_EMAIL)
        resp = login(client, ALICE_EMAIL, "Secret!1234")
        assert resp.status_code == 200
        # Sanity: alice's session works.
        assert client.get("/api/v1/auth/me").status_code == 200

        # Admin (separate client/session) deactivates alice via the API.
        admin_settings = client.app.state.settings
        admin_app = create_app(override_settings=admin_settings)

        from app.api.deps import get_db

        def override_get_db():
            yield test_db

        admin_app.dependency_overrides[get_db] = override_get_db
        with TC(admin_app) as admin_client:
            assert login(admin_client, "admin@interdec.com", "DecOps!2026").status_code == 200
            resp = admin_client.post(
                f"/api/v1/users/{alice.id}/status", json={"status": "deactivated"}
            )
            assert resp.status_code == 200

        # Alice's next request with the SAME session token is rejected:
        # deactivation took effect immediately.
        me = client.get("/api/v1/auth/me")
        assert me.status_code == 401

    def test_role_revocation_removes_admin_powers_immediately(self, client: TestClient, test_db):
        from fastapi.testclient import TestClient as TC

        from app.main import create_app

        from app.api.deps import get_db

        bob = make_user(test_db, email=BOB_EMAIL)
        admin_app = create_app(override_settings=client.app.state.settings)

        def override_get_db():
            yield test_db

        admin_app.dependency_overrides[get_db] = override_get_db

        # Grant bob the System Administrator role via the API.
        with TC(admin_app) as admin_client:
            assert login(admin_client, "admin@interdec.com", "DecOps!2026").status_code == 200
            from app.models import Role

            role = test_db.query(Role).filter_by(name="Company Administrator").first()
            resp = admin_client.post(f"/api/v1/users/{bob.id}/roles", json={"role_id": str(role.id)})
            assert resp.status_code == 200

        # Bob now holds users.manage - he can list users.
        assert login(client, BOB_EMAIL, "Secret!1234").status_code == 200
        assert client.get("/api/v1/users").status_code == 200

        # Revoke the role through the admin session; bob's next call is denied (404 policy).
        with TC(admin_app) as admin_client:
            assert login(admin_client, "admin@interdec.com", "DecOps!2026").status_code == 200
            from app.models import Role

            role = test_db.query(Role).filter_by(name="Company Administrator").first()
            assert admin_client.delete(f"/api/v1/users/{bob.id}/roles/{role.id}").status_code == 200

        assert client.get("/api/v1/users").status_code == 404
