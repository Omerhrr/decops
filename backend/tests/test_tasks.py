"""Phase 4 — Task Management API tests (spec exit criteria: "Users can manage
authorized tasks. All task mutations enforce authorization and validation.").

Covers: creation (AC-01), DEC-02 accountability, visibility modes through the
API, transition validation + authorization, assignment policy, access grants
with immediate revocation, cross-task isolation (AC-10/AC-11), optimistic
concurrency (AC-18), and the activity timeline (AC-12).
"""

import uuid

from fastapi.testclient import TestClient

from app.models import AccessLevel, Department, DepartmentMembership, MembershipRole, User, UserRole
from app.models.task import AssignmentRoleType
from tests.conftest import login, make_user


def _create_department(db, name: str, lead: User | None = None) -> Department:
    dept = Department(name=name, department_lead_user_id=lead.id if lead else None)
    db.add(dept)
    db.flush()
    if lead is not None:
        db.add(DepartmentMembership(
            department_id=dept.id, user_id=lead.id, membership_role=MembershipRole.lead,
        ))
    db.commit()
    db.refresh(dept)
    return dept


def _enroll(db, user: User, dept: Department) -> None:
    db.add(DepartmentMembership(department_id=dept.id, user_id=user.id))
    db.commit()


def _create_task(client: TestClient, *, pm_id: str, **overrides) -> dict:
    payload = {
        "title": "Deploy the new intranet",
        "description": "Migrate the intranet to the new hosting environment.",
        "priority": "high",
        "accountable_pm_id": pm_id,
        "due_date": "2026-12-31",
        "visibility_mode": "participants",
    }
    payload.update(overrides)
    response = client.post("/api/v1/tasks", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------

class TestTaskCreation:
    def test_creator_creates_task_with_number_and_accountability(self, client, test_db):
        admin = test_db.query(User).filter_by(email="admin@interdec.com").first()
        pm = make_user(test_db, email="pm1@interdec.com", role_names=["Accountable PM"])
        token = login(client, "admin@interdec.com", "DecOps!2026").cookies

        data = _create_task(client, pm_id=str(pm.id))

        assert data["task_number"].startswith("TSK-")
        assert data["status"] == "draft"
        assert data["accountable_pm"]["id"] == str(pm.id)
        assert data["visibility_mode"] == "participants"
        roles = [(a["assignment_role"], a["user"]["id"]) for a in data["assignments"]]
        assert ("accountable_pm", str(pm.id)) in roles
        # Activity history starts with the creation event (AC-12)
        activity = client.get(f"/api/v1/tasks/{data['id']}/activity").json()
        assert any(a["activity_type"] == "task.created" for a in activity)

    def test_task_numbers_are_unique_and_sequential(self, client, test_db):
        pm = make_user(test_db, email="pm2@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        first = _create_task(client, pm_id=str(pm.id))
        second = _create_task(client, pm_id=str(pm.id), title="Second effort")
        assert first["task_number"] != second["task_number"]

    def test_user_without_create_permission_gets_404(self, client, test_db):
        make_user(test_db, email="plain@interdec.com")  # Department Member
        login(client, "plain@interdec.com", "Secret!1234")
        response = client.post("/api/v1/tasks", json={
            "title": "Should not appear", "accountable_pm_id": str(uuid.uuid4()),
        })
        assert response.status_code == 404

    def test_invalid_visibility_mode_rejected(self, client, test_db):
        pm = make_user(test_db, email="pm3@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        response = client.post("/api/v1/tasks", json={
            "title": "Bad visibility", "accountable_pm_id": str(pm.id),
            "visibility_mode": "everyone",
        })
        assert response.status_code == 422

    def test_department_scoped_requires_department(self, client, test_db):
        pm = make_user(test_db, email="pm4@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        response = client.post("/api/v1/tasks", json={
            "title": "Scoped to nothing", "accountable_pm_id": str(pm.id),
            "visibility_mode": "department_scoped", "department_ids": [],
        })
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Visibility & isolation
# ---------------------------------------------------------------------------

class TestVisibilityAndIsolation:
    def test_private_task_hidden_from_outsiders(self, client, test_db):
        admin = test_db.query(User).filter_by(email="admin@interdec.com").first()
        pm = make_user(test_db, email="pm5@interdec.com", role_names=["Accountable PM"])
        outsider = make_user(test_db, email="out1@interdec.com", role_names=["Department Member"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id), visibility_mode="private")
        # Creator still sees their own task
        assert client.get(f"/api/v1/tasks/{task['id']}").status_code == 200
        login(client, "out1@interdec.com", "Secret!1234")
        assert client.get(f"/api/v1/tasks/{task['id']}").status_code == 404

    def test_participants_mode_shows_assigned_supporting_pm(self, client, test_db):
        pm = make_user(test_db, email="pm6@interdec.com", role_names=["Accountable PM"])
        support = make_user(test_db, email="sup1@interdec.com", role_names=["Supporting PM"])
        outsider = make_user(test_db, email="out2@interdec.com", role_names=["Department Member"])
        login(client, "pm6@interdec.com", "Secret!1234")
        task = _create_task(client, pm_id=str(pm.id))
        client.post(f"/api/v1/tasks/{task['id']}/assignments",
                    json={"user_id": str(support.id), "assignment_role": "supporting_pm"})
        login(client, "sup1@interdec.com", "Secret!1234")
        assert client.get(f"/api/v1/tasks/{task['id']}").status_code == 200
        login(client, "out2@interdec.com", "Secret!1234")
        assert client.get(f"/api/v1/tasks/{task['id']}").status_code == 404

    def test_department_scoped_view_needs_department_and_permission(self, client, test_db):
        pm = make_user(test_db, email="pm7@interdec.com", role_names=["Accountable PM"])
        lead = make_user(test_db, email="lead1@interdec.com", role_names=["Department Lead"])
        lead2 = make_user(test_db, email="lead2@interdec.com", role_names=["Department Lead"])
        dept1 = _create_department(test_db, "IT Operations", lead=lead)
        dept2 = _create_department(test_db, "Finance", lead=lead2)
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id), visibility_mode="department_scoped",
                            department_ids=[str(dept1.id)])
        login(client, "lead1@interdec.com", "Secret!1234")
        assert client.get(f"/api/v1/tasks/{task['id']}").status_code == 200
        login(client, "lead2@interdec.com", "Secret!1234")
        assert client.get(f"/api/v1/tasks/{task['id']}").status_code == 404

    def test_custom_grant_grants_and_revocation_applies_immediately(self, client, test_db):
        pm = make_user(test_db, email="pm8@interdec.com", role_names=["Accountable PM"])
        grantee = make_user(test_db, email="grantee1@interdec.com", role_names=["Read-Only Auditor"])
        login(client, "admin@interdec.com", "DecOps!2026")
        # custom tasks must be born with a valid policy: at least one grant
        task = _create_task(client, pm_id=str(pm.id), visibility_mode="custom",
                            grant_user_ids=[str(grantee.id)])
        assert client.get(f"/api/v1/tasks/{task['id']}").status_code == 200

        grant_id = client.get(f"/api/v1/tasks/{task['id']}").json()["access_grants"][0]["id"]
        assert client.delete(f"/api/v1/tasks/{task['id']}/access-grants/{grant_id}").status_code == 204
        # Immediate revocation, checked as the grantee (creator keeps access)
        assert client.get(f"/api/v1/tasks/{task['id']}").status_code == 200  # admin/creator
        login(client, "grantee1@interdec.com", "Secret!1234")
        assert client.get(f"/api/v1/tasks/{task['id']}").status_code == 404

        # Re-granting through the API restores access
        login(client, "admin@interdec.com", "DecOps!2026")
        response = client.post(f"/api/v1/tasks/{task['id']}/access-grants",
                               json={"user_id": str(grantee.id), "access_level": "view"})
        assert response.status_code == 201, response.text

    def test_explicit_denial_overrides_participation(self, client, test_db):
        pm = make_user(test_db, email="pm9@interdec.com", role_names=["Accountable PM"])
        support = make_user(test_db, email="sup2@interdec.com", role_names=["Supporting PM"])
        login(client, "pm9@interdec.com", "Secret!1234")
        task = _create_task(client, pm_id=str(pm.id))
        client.post(f"/api/v1/tasks/{task['id']}/assignments",
                    json={"user_id": str(support.id), "assignment_role": "supporting_pm"})
        login(client, "sup2@interdec.com", "Secret!1234")
        assert client.get(f"/api/v1/tasks/{task['id']}").status_code == 200

        # Creator grants with manage_all? No — use the admin to record a denial.
        login(client, "admin@interdec.com", "DecOps!2026")
        response = client.post(f"/api/v1/tasks/{task['id']}/access-grants",
                               json={"user_id": str(support.id), "access_level": "denied"})
        assert response.status_code == 201
        login(client, "sup2@interdec.com", "Secret!1234")
        assert client.get(f"/api/v1/tasks/{task['id']}").status_code == 404

    def test_grant_never_leaks_to_sibling_task(self, client, test_db):
        pm = make_user(test_db, email="pm10@interdec.com", role_names=["Accountable PM"])
        grantee = make_user(test_db, email="grantee2@interdec.com", role_names=["Read-Only Auditor"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task_a = _create_task(client, pm_id=str(pm.id), visibility_mode="custom",
                              title="Task A secret", grant_user_ids=[str(grantee.id)])
        task_b = _create_task(client, pm_id=str(pm.id), visibility_mode="custom",
                              title="Task B secret", grant_user_ids=[str(pm.id)])
        login(client, "grantee2@interdec.com", "Secret!1234")
        assert client.get(f"/api/v1/tasks/{task_a['id']}").status_code == 200
        # AC-10/AC-11: access to one task never grants another
        assert client.get(f"/api/v1/tasks/{task_b['id']}").status_code == 404
        listing = client.get("/api/v1/tasks").json()
        listed_ids = {t["id"] for t in listing["items"]}
        assert task_a["id"] in listed_ids and task_b["id"] not in listed_ids

    def test_register_lists_only_authorized_tasks(self, client, test_db):
        pm = make_user(test_db, email="pm11@interdec.com", role_names=["Accountable PM"])
        member = make_user(test_db, email="out3@interdec.com", role_names=["Department Member"])
        login(client, "admin@interdec.com", "DecOps!2026")
        _create_task(client, pm_id=str(pm.id), title="Visible to admin only")
        login(client, "out3@interdec.com", "Secret!1234")
        listing = client.get("/api/v1/tasks").json()
        assert listing["total"] == 0 and listing["items"] == []


# ---------------------------------------------------------------------------
# Editing (AC-18)
# ---------------------------------------------------------------------------

class TestTaskEditing:
    def _setup(self, client, test_db):
        pm = make_user(test_db, email="pm12@interdec.com", role_names=["Accountable PM"])
        viewer = make_user(test_db, email="viewer1@interdec.com", role_names=["Read-Only Auditor"])
        login(client, "pm12@interdec.com", "Secret!1234")
        task = _create_task(client, pm_id=str(pm.id))
        return pm, viewer, task

    def test_update_bumps_version_and_records_activity(self, client, test_db):
        pm, _, task = self._setup(client, test_db)
        data = client.patch(f"/api/v1/tasks/{task['id']}", json={
            "version": task["version"], "title": "Deploy the intranet v2",
            "percent_complete": 25,
        }).json()
        assert data["version"] == task["version"] + 1
        assert data["title"] == "Deploy the intranet v2"
        activity = client.get(f"/api/v1/tasks/{task['id']}/activity").json()
        assert any(a["activity_type"] == "task.updated" for a in activity)

    def test_stale_version_conflicts_409(self, client, test_db):
        pm, _, task = self._setup(client, test_db)
        response = client.patch(f"/api/v1/tasks/{task['id']}", json={
            "version": task["version"] + 5, "title": "Stale write",
        })
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "version_conflict"

    def test_view_only_user_cannot_edit(self, client, test_db):
        pm, viewer, task = self._setup(client, test_db)
        grant_response = client.post(f"/api/v1/tasks/{task['id']}/access-grants",
                                     json={"user_id": str(viewer.id), "access_level": "view"})
        assert grant_response.status_code == 201
        login(client, "viewer1@interdec.com", "Secret!1234")
        current_version = client.get(f"/api/v1/tasks/{task['id']}").json()["version"]
        response = client.patch(f"/api/v1/tasks/{task['id']}", json={
            "version": current_version, "title": "Hijack attempt",
        })
        assert response.status_code == 404  # view != update (spec task_visibility.rules)

    def test_update_ignores_unsent_fields(self, client, test_db):
        pm, _, task = self._setup(client, test_db)
        data = client.patch(f"/api/v1/tasks/{task['id']}", json={
            "version": task["version"], "priority": "critical",
        }).json()
        assert data["priority"] == "critical"
        assert data["description"] == task["description"]  # untouched
        assert data["percent_complete"] == task["percent_complete"]


# ---------------------------------------------------------------------------
# Lifecycle transitions
# ---------------------------------------------------------------------------

class TestTransitions:
    def _task_as_pm(self, client, test_db, email="pm13@interdec.com"):
        pm = make_user(test_db, email=email, role_names=["Accountable PM"])
        login(client, email, "Secret!1234")
        return pm, _create_task(client, pm_id="self-placeholder")

    def test_full_happy_path_with_reasons_and_timestamps(self, client, test_db):
        pm = make_user(test_db, email="pm14@interdec.com", role_names=["Accountable PM"])
        login(client, "pm14@interdec.com", "Secret!1234")
        task = _create_task(client, pm_id=str(pm.id))
        tid = task["id"]

        # draft -> open
        data = client.post(f"/api/v1/tasks/{tid}/transition", json={"to_status": "open"}).json()
        assert data["status"] == "open"
        # open -> in_progress
        data = client.post(f"/api/v1/tasks/{tid}/transition", json={"to_status": "in_progress"}).json()
        assert data["status"] == "in_progress"
        # in_progress -> blocked requires explanation
        response = client.post(f"/api/v1/tasks/{tid}/transition", json={"to_status": "blocked"})
        assert response.status_code == 422
        data = client.post(f"/api/v1/tasks/{tid}/transition", json={
            "to_status": "blocked", "reason": "Waiting for hosting credentials",
        }).json()
        assert data["status"] == "blocked"
        # blocked -> in_progress
        client.post(f"/api/v1/tasks/{tid}/transition", json={"to_status": "in_progress"})
        # in_progress -> under_review
        client.post(f"/api/v1/tasks/{tid}/transition", json={"to_status": "under_review"})
        # under_review -> completed
        data = client.post(f"/api/v1/tasks/{tid}/transition", json={"to_status": "completed"}).json()
        assert data["status"] == "completed" and data["completed_at"]
        # reopening requires a reason (spec transition_rules)
        response = client.post(f"/api/v1/tasks/{tid}/transition", json={"to_status": "in_progress"})
        assert response.status_code == 422
        data = client.post(f"/api/v1/tasks/{tid}/transition", json={
            "to_status": "in_progress", "reason": "Defect found in verification",
        }).json()
        assert data["status"] == "in_progress" and data["completed_at"] is None

    def test_invalid_transition_rejected(self, client, test_db):
        pm = make_user(test_db, email="pm15@interdec.com", role_names=["Accountable PM"])
        login(client, "pm15@interdec.com", "Secret!1234")
        task = _create_task(client, pm_id=str(pm.id))
        response = client.post(f"/api/v1/tasks/{task['id']}/transition",
                               json={"to_status": "in_progress"})  # draft skips to in_progress
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_transition"

    def test_cancelling_requires_reason(self, client, test_db):
        pm = make_user(test_db, email="pm16@interdec.com", role_names=["Accountable PM"])
        login(client, "pm16@interdec.com", "Secret!1234")
        task = _create_task(client, pm_id=str(pm.id))
        response = client.post(f"/api/v1/tasks/{task['id']}/transition",
                               json={"to_status": "cancelled"})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "reason_required"
        data = client.post(f"/api/v1/tasks/{task['id']}/transition", json={
            "to_status": "cancelled", "reason": "Superseded by another initiative",
        }).json()
        assert data["status"] == "cancelled" and data["cancelled_at"]

    def test_transition_options_endpoint(self, client, test_db):
        pm = make_user(test_db, email="pm17@interdec.com", role_names=["Accountable PM"])
        login(client, "pm17@interdec.com", "Secret!1234")
        task = _create_task(client, pm_id=str(pm.id))
        options = client.get(f"/api/v1/tasks/{task['id']}/transition-options").json()
        assert options["current_status"] == "draft"
        assert set(options["allowed_transitions"]) == {"open", "cancelled"}

    def test_scope_viewer_cannot_transition(self, client, test_db):
        lead = make_user(test_db, email="lead3@interdec.com", role_names=["Department Lead"])
        pm = make_user(test_db, email="pm18@interdec.com", role_names=["Accountable PM"])
        dept = _create_department(test_db, "Facilities", lead=lead)
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id), visibility_mode="department_scoped",
                            department_ids=[str(dept.id)])
        login(client, "lead3@interdec.com", "Secret!1234")
        assert client.get(f"/api/v1/tasks/{task['id']}").status_code == 200  # can view
        response = client.post(f"/api/v1/tasks/{task['id']}/transition",
                               json={"to_status": "open"})
        assert response.status_code == 404  # view != operate


# ---------------------------------------------------------------------------
# Assignments (DEC-02, MOD-003)
# ---------------------------------------------------------------------------

class TestAssignments:
    def test_replacing_accountable_pm_revokes_previous(self, client, test_db):
        pm1 = make_user(test_db, email="pm19@interdec.com", role_names=["Accountable PM"])
        pm2 = make_user(test_db, email="pm20@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm1.id))
        data = client.post(f"/api/v1/tasks/{task['id']}/assignments",
                           json={"user_id": str(pm2.id), "assignment_role": "accountable_pm"}).json()
        active = [a for a in data["assignments"] if a["revoked_at"] is None]
        accountable = [a for a in active if a["assignment_role"] == "accountable_pm"]
        assert len(accountable) == 1 and accountable[0]["user"]["id"] == str(pm2.id)
        assert data["accountable_pm"]["id"] == str(pm2.id)
        activity = client.get(f"/api/v1/tasks/{task['id']}/activity").json()
        assert any(a["activity_type"] == "task.accountable_pm_changed" for a in activity)

    def test_assigning_user_is_recorded(self, client, test_db):
        pm = make_user(test_db, email="pm21@interdec.com", role_names=["Accountable PM"])
        support = make_user(test_db, email="sup3@interdec.com", role_names=["Supporting PM"])
        login(client, "pm21@interdec.com", "Secret!1234")
        task = _create_task(client, pm_id=str(pm.id))
        data = client.post(f"/api/v1/tasks/{task['id']}/assignments",
                           json={"user_id": str(support.id), "assignment_role": "supporting_pm"}).json()
        row = next(a for a in data["assignments"]
                   if a["user"]["id"] == str(support.id) and a["revoked_at"] is None)
        admin = test_db.query(User).filter_by(email="admin@interdec.com").first()
        # pm created the task, so assigned_by must be the PM, not the admin
        assert row["assigned_by_id"] == str(pm.id) != str(admin.id)

    def test_deactivated_user_cannot_be_assigned(self, client, test_db):
        pm = make_user(test_db, email="pm22@interdec.com", role_names=["Accountable PM"])
        inactive = make_user(test_db, email="gone@interdec.com", status="deactivated")
        login(client, "pm22@interdec.com", "Secret!1234")
        task = _create_task(client, pm_id=str(pm.id))
        response = client.post(f"/api/v1/tasks/{task['id']}/assignments",
                               json={"user_id": str(inactive.id), "assignment_role": "supporting_pm"})
        assert response.status_code == 422

    def test_department_scoped_task_rejects_outside_assignee(self, client, test_db):
        lead = make_user(test_db, email="lead4@interdec.com", role_names=["Department Lead"])
        pm = make_user(test_db, email="pm23@interdec.com", role_names=["Accountable PM"])
        outsider = make_user(test_db, email="out4@interdec.com", role_names=["Supporting PM"])
        dept = _create_department(test_db, "Logistics", lead=lead)
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id), visibility_mode="department_scoped",
                            department_ids=[str(dept.id)])
        # The PM (no tasks.manage_all) may only assign from participating departments.
        login(client, "pm23@interdec.com", "Secret!1234")
        response = client.post(f"/api/v1/tasks/{task['id']}/assignments",
                               json={"user_id": str(outsider.id), "assignment_role": "supporting_pm"})
        assert response.status_code == 422
        assert "department" in response.json()["error"]["message"]

    def test_cannot_revoke_the_only_accountable_pm(self, client, test_db):
        pm = make_user(test_db, email="pm24@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        assignment_id = next(a["id"] for a in task["assignments"]
                             if a["assignment_role"] == "accountable_pm")
        response = client.delete(f"/api/v1/tasks/{task['id']}/assignments/{assignment_id}")
        assert response.status_code == 409

    def test_user_without_assign_permission_gets_404(self, client, test_db):
        pm = make_user(test_db, email="pm25@interdec.com", role_names=["Accountable PM"])
        member = make_user(test_db, email="member1@interdec.com", role_names=["Department Member"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        # member cannot even see the task, let alone assign
        login(client, "member1@interdec.com", "Secret!1234")
        response = client.post(f"/api/v1/tasks/{task['id']}/assignments",
                               json={"user_id": str(member.id), "assignment_role": "supporting_pm"})
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Departments, grants permissions, activity
# ---------------------------------------------------------------------------

class TestDepartmentsAndActivity:
    def test_link_department_and_duplicate_conflict(self, client, test_db):
        pm = make_user(test_db, email="pm26@interdec.com", role_names=["Accountable PM"])
        dept = _create_department(test_db, "Customer Service")
        login(client, "pm26@interdec.com", "Secret!1234")
        task = _create_task(client, pm_id=str(pm.id))
        data = client.post(f"/api/v1/tasks/{task['id']}/departments",
                           json={"department_id": str(dept.id)}).json()
        assert any(td["department_id"] == str(dept.id) for td in data["task_departments"])
        assert dept.name in data["department_names"]
        response = client.post(f"/api/v1/tasks/{task['id']}/departments",
                               json={"department_id": str(dept.id)})
        assert response.status_code == 409

    def test_plain_participant_cannot_change_access(self, client, test_db):
        pm = make_user(test_db, email="pm27@interdec.com", role_names=["Accountable PM"])
        worker = make_user(test_db, email="worker1@interdec.com", role_names=["Department Member"])
        other = make_user(test_db, email="other1@interdec.com", role_names=["Department Member"])
        login(client, "pm27@interdec.com", "Secret!1234")
        task = _create_task(client, pm_id=str(pm.id))
        client.post(f"/api/v1/tasks/{task['id']}/assignments",
                    json={"user_id": str(worker.id), "assignment_role": "work_item_assignee"})
        # A participant without tasks.update_assigned can contribute but never
        # restructure access (engine operation matrix, Phase 3 semantics).
        login(client, "worker1@interdec.com", "Secret!1234")
        response = client.post(f"/api/v1/tasks/{task['id']}/access-grants",
                               json={"user_id": str(other.id), "access_level": "view"})
        assert response.status_code == 404

    def test_activity_timeline_records_everything(self, client, test_db):
        pm = make_user(test_db, email="pm28@interdec.com", role_names=["Accountable PM"])
        support = make_user(test_db, email="sup5@interdec.com", role_names=["Supporting PM"])
        dept = _create_department(test_db, "Quality")
        login(client, "pm28@interdec.com", "Secret!1234")
        task = _create_task(client, pm_id=str(pm.id))
        client.post(f"/api/v1/tasks/{task['id']}/transition", json={"to_status": "open"})
        client.post(f"/api/v1/tasks/{task['id']}/assignments",
                    json={"user_id": str(support.id), "assignment_role": "supporting_pm"})
        client.post(f"/api/v1/tasks/{task['id']}/departments",
                    json={"department_id": str(dept.id)})
        client.patch(f"/api/v1/tasks/{task['id']}", json={"version": 3, "percent_complete": 10})

        activity = client.get(f"/api/v1/tasks/{task['id']}/activity").json()
        types = [a["activity_type"] for a in activity]
        assert types.count("task.created") == 1
        assert "task.status_changed" in types
        assert "task.assigned" in types
        assert "task.department_added" in types
        assert "task.updated" in types
        # newest first, actors named
        assert activity[0]["actor"]["id"] == str(pm.id)
