"""Department management API tests : CRUD, memberships,
lead handling, authorization boundaries, and audit trail."""

from fastapi.testclient import TestClient

from app.models import AuditEvent
from tests.conftest import login, make_user


def admin_client(client: TestClient) -> TestClient:
    assert login(client, "admin@interdec.com", "DecOps!2026").status_code == 200
    return client


class TestDepartmentCrud:
    def test_admin_can_create_department(self, client: TestClient, test_db):
        admin_client(client)
        resp = client.post(
            "/api/v1/departments",
            json={"name": "Operations", "description": "Core ops team"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Operations"
        assert body["status"] == "active"
        assert body["member_count"] == 0

    def test_duplicate_name_conflicts(self, client: TestClient, test_db):
        admin_client(client)
        client.post("/api/v1/departments", json={"name": "Finance"})
        resp = client.post("/api/v1/departments", json={"name": "Finance"})
        assert resp.status_code == 409

    def test_create_with_lead_adds_lead_membership(self, client: TestClient, test_db):
        lead = make_user(test_db, email="dept.lead@interdec.com")
        admin_client(client)
        resp = client.post(
            "/api/v1/departments", json={"name": "Engineering", "lead_user_id": str(lead.id)}
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["lead"]["id"] == str(lead.id)
        assert body["member_count"] == 1
        assert body["memberships"][0]["membership_role"] == "lead"

    def test_update_department_is_audited(self, client: TestClient, test_db):
        admin_client(client)
        dept = client.post("/api/v1/departments", json={"name": "Support"}).json()
        resp = client.patch(
            f"/api/v1/departments/{dept['id']}",
            json={"description": "Customer support", "status": "inactive"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "inactive"

        event = (
            test_db.query(AuditEvent)
            .filter_by(action="department.updated", resource_id=dept["id"])
            .one()
        )
        assert "description changed" in event.change_summary
        assert "status changed" in event.change_summary

    def test_list_requires_permission(self, client: TestClient, test_db):
        admin_client(client)
        assert client.get("/api/v1/departments").status_code == 200
        client.post("/api/v1/auth/logout")
        make_user(test_db, email="plain.member@interdec.com")
        login(client, "plain.member@interdec.com", "Secret!1234")
        assert client.get("/api/v1/departments").status_code == 404


class TestMemberships:
    def test_add_and_remove_member_audited(self, client: TestClient, test_db):
        member = make_user(test_db, email="ops.member@interdec.com")
        admin_client(client)
        dept = client.post("/api/v1/departments", json={"name": "Logistics"}).json()

        resp = client.post(
            f"/api/v1/departments/{dept['id']}/members",
            json={"user_id": str(member.id), "membership_role": "member"},
        )
        assert resp.status_code == 201
        assert resp.json()["member_count"] == 1

        resp = client.delete(f"/api/v1/departments/{dept['id']}/members/{member.id}")
        assert resp.status_code == 204

        actions = [
            e.action
            for e in test_db.query(AuditEvent)
            .filter_by(resource_type="department", resource_id=dept["id"])
            .all()
        ]
        assert "department.member_added" in actions
        assert "department.member_removed" in actions

    def test_duplicate_membership_conflicts(self, client: TestClient, test_db):
        member = make_user(test_db, email="dupe.member@interdec.com")
        admin_client(client)
        dept = client.post("/api/v1/departments", json={"name": "Duplicates"}).json()
        payload = {"user_id": str(member.id)}
        assert client.post(f"/api/v1/departments/{dept['id']}/members", json=payload).status_code == 201
        assert client.post(f"/api/v1/departments/{dept['id']}/members", json=payload).status_code == 409

    def test_employee_can_belong_to_multiple_departments(self, client: TestClient, test_db):
        """Spec : support employees belonging to multiple departments."""
        member = make_user(test_db, email="multi.member@interdec.com")
        admin_client(client)
        d1 = client.post("/api/v1/departments", json={"name": "Dept One"}).json()
        d2 = client.post("/api/v1/departments", json={"name": "Dept Two"}).json()
        for d in (d1, d2):
            resp = client.post(
                f"/api/v1/departments/{d['id']}/members", json={"user_id": str(member.id)}
            )
            assert resp.status_code == 201
        # Direct check via user detail
        detail = client.get(f"/api/v1/users/{member.id}").json()
        assert len(detail["memberships"]) == 2

    def test_remove_non_member_is_idempotent(self, client: TestClient, test_db):
        stranger = make_user(test_db, email="stranger.person@interdec.com")
        admin_client(client)
        dept = client.post("/api/v1/departments", json={"name": "Empty Dept"}).json()
        resp = client.delete(f"/api/v1/departments/{dept['id']}/members/{stranger.id}")
        assert resp.status_code == 204
