"""User administration API tests (MOD-002 Phase 3): CRUD, role assignment,
deactivation, authorization boundaries, and audit trail writes."""

import uuid

from fastapi.testclient import TestClient

from app.models import AuditEvent, Role, User
from tests.conftest import login, make_user

NEW_USER = {
    "email": "new.employee@interdec.com",
    "full_name": "New Employee",
    "employee_code": "INT-9001",
    "password": "Sup3rSecret!Pass",
}


def admin_client(client: TestClient) -> TestClient:
    assert login(client, "admin@interdec.com", "DecOps!2026").status_code == 200
    return client


class TestCreateUser:
    def test_admin_can_create_employee(self, client: TestClient, test_db):
        admin_client(client)
        resp = client.post("/api/v1/users", json=NEW_USER)
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == "new.employee@interdec.com"
        assert body["account_status"] == "active"
        assert "password" not in body

    def test_duplicate_email_conflicts(self, client: TestClient, test_db):
        admin_client(client)
        client.post("/api/v1/users", json=NEW_USER)
        resp = client.post("/api/v1/users", json=NEW_USER)
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "email_taken"

    def test_short_password_rejected(self, client: TestClient, test_db):
        admin_client(client)
        resp = client.post("/api/v1/users", json={**NEW_USER, "password": "short"})
        assert resp.status_code == 422

    def test_non_admin_gets_404_not_403(self, client: TestClient, test_db):
        make_user(test_db, email="pleb@interdec.com")
        login(client, "pleb@interdec.com", "Secret!1234")
        assert client.get("/api/v1/users").status_code == 404
        assert client.post("/api/v1/users", json=NEW_USER).status_code == 404

    def test_anonymous_unauthenticated(self, client: TestClient, test_db):
        assert client.post("/api/v1/users", json=NEW_USER).status_code == 401


class TestUpdateAndStatus:
    def test_update_full_name_is_audited(self, client: TestClient, test_db):
        admin_client(client)
        created = client.post("/api/v1/users", json=NEW_USER).json()
        resp = client.patch(f"/api/v1/users/{created['id']}", json={"full_name": "Renamed Person"})
        assert resp.status_code == 200
        assert resp.json()["full_name"] == "Renamed Person"

        event = (
            test_db.query(AuditEvent)
            .filter_by(action="user.updated", resource_id=created["id"])
            .one()
        )
        assert "full_name changed" in event.change_summary

    def test_deactivate_revokes_sessions_and_audits(self, client: TestClient, test_db):
        user = make_user(test_db, email="victim@interdec.com")
        assert login(client, "victim@interdec.com", "Secret!1234").status_code == 200

        admin_client(client)
        resp = client.post(
            f"/api/v1/users/{user.id}/status",
            json={"status": "deactivated", "reason": "employee departure"},
        )
        assert resp.status_code == 200
        assert resp.json()["account_status"] == "deactivated"

        event = (
            test_db.query(AuditEvent)
            .filter_by(action="user.status_changed", resource_id=str(user.id))
            .one()
        )
        assert event.reason == "employee departure"
        assert event.metadata_json["sessions_revoked"] is True

    def test_admin_cannot_deactivate_self(self, client: TestClient, test_db):
        admin_client(client)
        me = client.get("/api/v1/auth/me").json()
        resp = client.post(f"/api/v1/users/{me['id']}/status", json={"status": "deactivated"})
        assert resp.status_code == 422


class TestRoleAssignment:
    def test_assign_and_revoke_role_audited(self, client: TestClient, test_db):
        user = make_user(test_db, email="roled.person@interdec.com")
        admin_client(client)

        role = test_db.query(Role).filter_by(name="Accountable PM").first()
        resp = client.post(f"/api/v1/users/{user.id}/roles", json={"role_id": str(role.id)})
        assert resp.status_code == 200
        role_names = [r["name"] for r in resp.json()["roles"]]
        assert "Accountable PM" in role_names

        resp = client.delete(f"/api/v1/users/{user.id}/roles/{role.id}")
        assert resp.status_code == 200
        role_names = [r["name"] for r in resp.json()["roles"]]
        assert "Accountable PM" not in role_names

        actions = [
            e.action
            for e in test_db.query(AuditEvent)
            .filter_by(resource_type="user", resource_id=str(user.id))
            .all()
        ]
        assert "rbac.role_assigned" in actions
        assert "rbac.role_revoked" in actions

    def test_assign_unknown_role_404(self, client: TestClient, test_db):
        user = make_user(test_db, email="no.role@interdec.com")
        admin_client(client)
        resp = client.post(f"/api/v1/users/{user.id}/roles", json={"role_id": str(uuid.uuid4())})
        assert resp.status_code == 404

    def test_role_assignment_requires_roles_assign_permission(self, client: TestClient, test_db):
        user = make_user(test_db, email="target.person@interdec.com")
        # Plain member with only users.manage would still fail roles.assign,
        # but a plain Department Member has neither: 404.
        make_user(test_db, email="actor.member@interdec.com")
        login(client, "actor.member@interdec.com", "Secret!1234")
        role = test_db.query(Role).first()
        resp = client.post(f"/api/v1/users/{user.id}/roles", json={"role_id": str(role.id)})
        assert resp.status_code == 404


class TestRolesCatalogue:
    def test_list_roles_includes_permissions(self, client: TestClient, test_db):
        admin_client(client)
        resp = client.get("/api/v1/roles")
        assert resp.status_code == 200
        roles = resp.json()["items"]
        company_admin = next(r for r in roles if r["name"] == "Company Administrator")
        assert "users.manage" in company_admin["permissions"]
        assert "roles.assign" in company_admin["permissions"]
        system_admin = next(r for r in roles if r["name"] == "System Administrator")
        assert "system.config.manage" in system_admin["permissions"]
        # Per spec matrix, System Administrator does NOT manage users.
        assert "users.manage" not in system_admin["permissions"]
        assert all(r["is_system_role"] for r in roles)

    def test_list_permissions(self, client: TestClient, test_db):
        admin_client(client)
        resp = client.get("/api/v1/roles/permissions")
        assert resp.status_code == 200
        codes = [p["code"] for p in resp.json()["items"]]
        assert "users.manage" in codes and "departments.manage" in codes
