"""Phase 5 — Workflow Engine API tests (MOD-004).

Covers: stage/item CRUD + transitions, sequential gating through the API,
dependency cycle rejection, blockers, milestone auto-completion cascade,
progress calculation + manual/calculated modes (AC-06), optimistic
concurrency on work items (AC-18), authorization (view/operate grants,
outsider 404s) and audit + activity records.
"""

import uuid

from fastapi.testclient import TestClient

from app.models import AccessLevel, User
from tests.conftest import login, make_user


def _create_task(client: TestClient, *, pm_id: str, **overrides) -> dict:
    payload = {
        "title": "Roll out the CRM integration",
        "priority": "high",
        "accountable_pm_id": pm_id,
        "visibility_mode": "participants",
    }
    payload.update(overrides)
    response = client.post("/api/v1/tasks", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _start_task(client: TestClient, task_id: str) -> None:
    """draft -> open -> in_progress (task lifecycle transitions)."""
    response = client.post(
        f"/api/v1/tasks/{task_id}/transition", json={"to_status": "open"}
    )
    assert response.status_code == 200, response.text
    response = client.post(
        f"/api/v1/tasks/{task_id}/transition", json={"to_status": "in_progress"}
    )
    assert response.status_code == 200, response.text


def _stage(client: TestClient, task_id: str, name: str = "Discovery", **overrides) -> dict:
    payload = {"name": name, **overrides}
    response = client.post(f"/api/v1/tasks/{task_id}/stages", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _item(client: TestClient, task_id: str, stage_id: str, title: str = "Kickoff",
          item_type: str = "subtask", **overrides) -> dict:
    payload = {"item_type": item_type, "title": title, **overrides}
    response = client.post(f"/api/v1/tasks/{task_id}/stages/{stage_id}/items", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------

class TestStagesAPI:
    def test_create_list_and_tree(self, client, test_db):
        pm = make_user(test_db, email="pm-wf1@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        s1 = _stage(client, task["id"], "Discovery")
        s2 = _stage(client, task["id"], "Build", execution_mode="parallel")
        assert s1["sequence_number"] == 1
        assert s2["sequence_number"] == 2
        assert s2["execution_mode"] == "parallel"

        tree = client.get(f"/api/v1/tasks/{task['id']}/workflow").json()
        assert [s["name"] for s in tree["stages"]] == ["Discovery", "Build"]
        assert tree["task_status"] == "draft"
        assert tree["calculated_percent"] == 0
        assert tree["progress"]["method"]

    def test_sequence_insert_positions_and_reorder(self, client, test_db):
        pm = make_user(test_db, email="pm-wf2@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        _stage(client, task["id"], "One")
        _stage(client, task["id"], "Three")
        inserted = _stage(client, task["id"], "Two", sequence_number=2)
        tree = client.get(f"/api/v1/tasks/{task['id']}/workflow").json()
        assert [s["name"] for s in tree["stages"]] == ["One", "Two", "Three"]
        assert inserted["sequence_number"] == 2

        # Move "Three" to position 1.
        three = tree["stages"][2]
        response = client.patch(
            f"/api/v1/tasks/{task['id']}/stages/{three['id']}",
            json={"sequence_number": 1},
        )
        assert response.status_code == 200, response.text
        tree = client.get(f"/api/v1/tasks/{task['id']}/workflow").json()
        assert [s["name"] for s in tree["stages"]] == ["Three", "One", "Two"]

    def test_stage_transitions_gated_on_task_status(self, client, test_db):
        pm = make_user(test_db, email="pm-wf3@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        stage = _stage(client, task["id"])
        # Task is draft: workflow work cannot start yet.
        response = client.post(
            f"/api/v1/tasks/{task['id']}/stages/{stage['id']}/transition",
            json={"to_status": "in_progress"},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "task_not_in_progress"

        _start_task(client, task["id"])
        response = client.post(
            f"/api/v1/tasks/{task['id']}/stages/{stage['id']}/transition",
            json={"to_status": "in_progress"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "in_progress"

    def test_sequential_stage_blocked_until_earlier_completes(self, client, test_db):
        pm = make_user(test_db, email="pm-wf4@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        s1 = _stage(client, task["id"], "First")
        s2 = _stage(client, task["id"], "Second", execution_mode="parallel")
        s3 = _stage(client, task["id"], "Third")
        _start_task(client, task["id"])

        tree = client.get(f"/api/v1/tasks/{task['id']}/workflow").json()
        actionable = set(tree["actionable_stage_ids"])
        assert str(s1["id"]) in actionable
        assert str(s2["id"]) in actionable  # parallel starts immediately
        assert str(s3["id"]) not in actionable

        # Starting the sequential Third stage is rejected while First runs.
        response = client.post(
            f"/api/v1/tasks/{task['id']}/stages/{s3['id']}/transition",
            json={"to_status": "in_progress"},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "stage_not_actionable"

        # Start then complete First, then the parallel Second (no items ->
        # allowed); only when BOTH earlier stages are done does Third become
        # actionable (sequential gates on every lower-numbered stage).
        client.post(f"/api/v1/tasks/{task['id']}/stages/{s1['id']}/transition",
                    json={"to_status": "in_progress"})
        client.post(f"/api/v1/tasks/{task['id']}/stages/{s1['id']}/transition",
                    json={"to_status": "completed"})
        response = client.post(
            f"/api/v1/tasks/{task['id']}/stages/{s3['id']}/transition",
            json={"to_status": "in_progress"},
        )
        assert response.status_code == 409  # parallel stage 2 still running

        client.post(f"/api/v1/tasks/{task['id']}/stages/{s2['id']}/transition",
                    json={"to_status": "in_progress"})
        client.post(f"/api/v1/tasks/{task['id']}/stages/{s2['id']}/transition",
                    json={"to_status": "completed"})
        response = client.post(
            f"/api/v1/tasks/{task['id']}/stages/{s3['id']}/transition",
            json={"to_status": "in_progress"},
        )
        assert response.status_code == 200

    def test_stage_completion_requires_required_items(self, client, test_db):
        pm = make_user(test_db, email="pm-wf5@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        stage = _stage(client, task["id"])
        _item(client, task["id"], stage["id"], "Requirement gathering")
        _item(client, task["id"], stage["id"], "Nice to have", is_required=False)
        _start_task(client, task["id"])
        client.post(f"/api/v1/tasks/{task['id']}/stages/{stage['id']}/transition",
                    json={"to_status": "in_progress"})

        response = client.post(
            f"/api/v1/tasks/{task['id']}/stages/{stage['id']}/transition",
            json={"to_status": "completed"},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "stage_items_incomplete"
        assert "Requirement gathering" in response.json()["error"]["message"]

    def test_cancel_stage_requires_reason(self, client, test_db):
        pm = make_user(test_db, email="pm-wf6@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        stage = _stage(client, task["id"])
        response = client.post(
            f"/api/v1/tasks/{task['id']}/stages/{stage['id']}/transition",
            json={"to_status": "cancelled"},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "reason_required"

        response = client.post(
            f"/api/v1/tasks/{task['id']}/stages/{stage['id']}/transition",
            json={"to_status": "cancelled", "reason": "Scope dropped by client"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_delete_rules(self, client, test_db):
        pm = make_user(test_db, email="pm-wf7@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        stage = _stage(client, task["id"])
        _item(client, task["id"], stage["id"], "Blocked deletion")

        response = client.delete(f"/api/v1/tasks/{task['id']}/stages/{stage['id']}")
        assert response.status_code == 409  # stage not empty

        # Empty pending stage deletes fine and renumbers followers.
        s2 = _stage(client, task["id"], "Empty")
        s3 = _stage(client, task["id"], "After")
        response = client.delete(f"/api/v1/tasks/{task['id']}/stages/{s2['id']}")
        assert response.status_code == 204
        tree = client.get(f"/api/v1/tasks/{task['id']}/workflow").json()
        assert [s["sequence_number"] for s in tree["stages"]] == [1, 2]
        assert s3["id"] in {s["id"] for s in tree["stages"]}


# ---------------------------------------------------------------------------
# Work items
# ---------------------------------------------------------------------------

class TestWorkItemsAPI:
    def test_item_crud_and_nesting(self, client, test_db):
        pm = make_user(test_db, email="pm-wf8@interdec.com", role_names=["Accountable PM"])
        employee = make_user(test_db, email="emp-wf8@interdec.com")
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        stage = _stage(client, task["id"], "Delivery")

        milestone = _item(client, task["id"], stage["id"], "MVP live",
                          item_type="milestone")
        subtask = _item(client, task["id"], stage["id"], "Wire the API",
                        item_type="subtask", parent_work_item_id=milestone["id"],
                        assigned_user_id=str(employee.id))
        assert subtask["parent_work_item_id"] == milestone["id"]
        assert subtask["assignee"]["id"] == str(employee.id)

        # Subtask cannot nest under a subtask.
        response = client.post(
            f"/api/v1/tasks/{task['id']}/stages/{stage['id']}/items",
            json={"item_type": "subtask", "title": "Nope",
                  "parent_work_item_id": subtask["id"]},
        )
        assert response.status_code == 422

        # Parent milestone must live in the same stage.
        stage2 = _stage(client, task["id"], "Elsewhere")
        response = client.post(
            f"/api/v1/tasks/{task['id']}/stages/{stage2['id']}/items",
            json={"item_type": "subtask", "title": "Cross-stage child",
                  "parent_work_item_id": milestone["id"]},
        )
        assert response.status_code == 422

    def test_blocked_item_cannot_start(self, client, test_db):
        pm = make_user(test_db, email="pm-wf9@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        stage = _stage(client, task["id"], "Build")
        first = _item(client, task["id"], stage["id"], "Foundation")
        second = _item(client, task["id"], stage["id"], "Walls")
        client.post(f"/api/v1/tasks/{task['id']}/dependencies",
                    json={"predecessor_id": first["id"], "successor_id": second["id"]})
        _start_task(client, task["id"])

        response = client.post(
            f"/api/v1/tasks/{task['id']}/items/{second['id']}/transition",
            json={"to_status": "in_progress"},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "item_blocked"

        # The tree marks the blocker explicitly.
        tree = client.get(f"/api/v1/tasks/{task['id']}/workflow").json()
        blockers = {b["item_id"]: b["blocked_by"] for b in tree["blockers"]}
        assert blockers[str(second["id"])] == [str(first["id"])]

        # Complete the predecessor -> successor can start.
        client.post(f"/api/v1/tasks/{task['id']}/items/{first['id']}/transition",
                    json={"to_status": "in_progress"})
        client.post(f"/api/v1/tasks/{task['id']}/items/{first['id']}/transition",
                    json={"to_status": "completed"})
        response = client.post(
            f"/api/v1/tasks/{task['id']}/items/{second['id']}/transition",
            json={"to_status": "in_progress"},
        )
        assert response.status_code == 200

    def test_dependency_cycle_rejected_through_api(self, client, test_db):
        pm = make_user(test_db, email="pm-wf10@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        stage = _stage(client, task["id"])
        a = _item(client, task["id"], stage["id"], "A")
        b = _item(client, task["id"], stage["id"], "B")
        c = _item(client, task["id"], stage["id"], "C")

        client.post(f"/api/v1/tasks/{task['id']}/dependencies",
                    json={"predecessor_id": a["id"], "successor_id": b["id"]})
        client.post(f"/api/v1/tasks/{task['id']}/dependencies",
                    json={"predecessor_id": b["id"], "successor_id": c["id"]})

        response = client.post(f"/api/v1/tasks/{task['id']}/dependencies",
                               json={"predecessor_id": c["id"], "successor_id": a["id"]})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "dependency_cycle"

        # Duplicates and self-dependencies are rejected too.
        response = client.post(f"/api/v1/tasks/{task['id']}/dependencies",
                               json={"predecessor_id": a["id"], "successor_id": b["id"]})
        assert response.status_code == 409
        response = client.post(f"/api/v1/tasks/{task['id']}/dependencies",
                               json={"predecessor_id": a["id"], "successor_id": a["id"]})
        assert response.status_code == 422

    def test_milestone_auto_completes_with_last_subtask(self, client, test_db):
        pm = make_user(test_db, email="pm-wf11@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        stage = _stage(client, task["id"], "Delivery")
        milestone = _item(client, task["id"], stage["id"], "Go live", item_type="milestone")
        sub1 = _item(client, task["id"], stage["id"], "Data migration",
                     item_type="subtask", parent_work_item_id=milestone["id"])
        sub2 = _item(client, task["id"], stage["id"], "User training",
                     item_type="subtask", parent_work_item_id=milestone["id"])
        _start_task(client, task["id"])

        # Manual completion of the milestone is rejected while subtasks are open.
        client.post(f"/api/v1/tasks/{task['id']}/items/{milestone['id']}/transition",
                    json={"to_status": "in_progress"})
        response = client.post(
            f"/api/v1/tasks/{task['id']}/items/{milestone['id']}/transition",
            json={"to_status": "completed"},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "milestone_subtasks_incomplete"

        for sub in (sub1, sub2):
            client.post(f"/api/v1/tasks/{task['id']}/items/{sub['id']}/transition",
                        json={"to_status": "in_progress"})
            client.post(f"/api/v1/tasks/{task['id']}/items/{sub['id']}/transition",
                        json={"to_status": "completed"})

        milestone_row = client.get(f"/api/v1/tasks/{task['id']}/workflow").json()
        by_id = {i["id"]: i for i in milestone_row["items"]}
        assert by_id[milestone["id"]]["status"] == "completed"
        assert by_id[milestone["id"]]["completed_at"] is not None

        # Reopening a subtask reopens the milestone (consistency cascade).
        client.post(f"/api/v1/tasks/{task['id']}/items/{sub1['id']}/transition",
                    json={"to_status": "in_progress", "reason": "Defect found in migration"})
        refreshed = client.get(f"/api/v1/tasks/{task['id']}/workflow").json()
        by_id = {i["id"]: i for i in refreshed["items"]}
        assert by_id[milestone["id"]]["status"] == "in_progress"

    def test_optimistic_concurrency_on_items(self, client, test_db):
        pm = make_user(test_db, email="pm-wf12@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        stage = _stage(client, task["id"])
        item = _item(client, task["id"], stage["id"], "Original title")

        first = client.patch(
            f"/api/v1/tasks/{task['id']}/items/{item['id']}",
            json={"title": "First edit", "version": item["version"]},
        )
        assert first.status_code == 200
        assert first.json()["version"] == item["version"] + 1

        stale = client.patch(
            f"/api/v1/tasks/{task['id']}/items/{item['id']}",
            json={"title": "Stale edit", "version": item["version"]},
        )
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "version_conflict"

    def test_assign_and_unassign_records_actor(self, client, test_db):
        pm = make_user(test_db, email="pm-wf13@interdec.com", role_names=["Accountable PM"])
        employee = make_user(test_db, email="emp-wf13@interdec.com")
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        stage = _stage(client, task["id"])
        item = _item(client, task["id"], stage["id"], "Shared deliverable")

        response = client.post(
            f"/api/v1/tasks/{task['id']}/items/{item['id']}/assign",
            json={"assigned_user_id": str(employee.id)},
        )
        assert response.status_code == 200
        assert response.json()["assignee"]["id"] == str(employee.id)

        # Inactive users cannot be assigned.
        inactive = make_user(test_db, email="ghost-wf13@interdec.com", status="deactivated")
        response = client.post(
            f"/api/v1/tasks/{task['id']}/items/{item['id']}/assign",
            json={"assigned_user_id": str(inactive.id)},
        )
        assert response.status_code == 422

        response = client.post(
            f"/api/v1/tasks/{task['id']}/items/{item['id']}/assign",
            json={"assigned_user_id": None},
        )
        assert response.status_code == 200
        assert response.json()["assignee"] is None


# ---------------------------------------------------------------------------
# Progress (AC-06)
# ---------------------------------------------------------------------------

class TestProgressAPI:
    def _build_workflow(self, client, test_db, email: str) -> dict:
        pm = make_user(test_db, email=email, role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        s1 = _stage(client, task["id"], "Setup", weight=1)
        s2 = _stage(client, task["id"], "Rollout", weight=3, execution_mode="parallel")
        i1 = _item(client, task["id"], s1["id"], "Provision", weight=1)
        _item(client, task["id"], s2["id"], "Training", weight=1, is_required=False)
        _start_task(client, task["id"])
        return {"task": task, "s1": s1, "s2": s2, "i1": i1}

    def test_calculated_mode_syncs_percent_and_rejects_manual(self, client, test_db):
        data = self._build_workflow(client, test_db, "pm-wf14@interdec.com")
        task = data["task"]

        response = client.post(
            f"/api/v1/tasks/{task['id']}/workflow-settings",
            json={"progress_mode": "calculated"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["calculated_percent"] == 0

        # Complete the only counted item -> task progress 25% (1/4 weighted).
        client.post(f"/api/v1/tasks/{task['id']}/items/{data['i1']['id']}/transition",
                    json={"to_status": "in_progress"})
        client.post(f"/api/v1/tasks/{task['id']}/items/{data['i1']['id']}/transition",
                    json={"to_status": "completed"})

        tree = client.get(f"/api/v1/tasks/{task['id']}/workflow").json()
        assert tree["calculated_percent"] == 25
        detail = client.get(f"/api/v1/tasks/{task['id']}").json()
        assert detail["percent_complete"] == 25  # synced automatically
        assert detail["progress_mode"] == "calculated"

        # Manual percent entry is now rejected with a clear conflict.
        response = client.patch(
            f"/api/v1/tasks/{task['id']}",
            json={"percent_complete": 80, "version": detail["version"]},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "progress_is_calculated"

        # The calculation method is visible to authorized users (AC-06).
        method_text = tree["progress"]["method"].lower()
        assert "weighted" in method_text
        stage_breakdown = {s["stage_name"]: s for s in tree["progress"]["stages"]}
        assert stage_breakdown["Setup"]["method"]
        assert stage_breakdown["Rollout"]["excluded"].get("optional") == 1

    def test_switching_back_to_manual_allows_overrides(self, client, test_db):
        data = self._build_workflow(client, test_db, "pm-wf15@interdec.com")
        task = data["task"]
        client.post(f"/api/v1/tasks/{task['id']}/workflow-settings",
                    json={"progress_mode": "calculated"})
        response = client.post(f"/api/v1/tasks/{task['id']}/workflow-settings",
                               json={"progress_mode": "manual", "reason": "PM override for reporting"})
        assert response.status_code == 200

        detail = client.get(f"/api/v1/tasks/{task['id']}").json()
        response = client.patch(
            f"/api/v1/tasks/{task['id']}",
            json={"percent_complete": 40, "version": detail["version"]},
        )
        assert response.status_code == 200

        activity = client.get(f"/api/v1/tasks/{task['id']}/activity").json()
        types = [a["activity_type"] for a in activity]
        assert "workflow.progress_mode_changed" in types


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------

class TestWorkflowAuthorization:
    def test_outsider_gets_404_not_403(self, client, test_db):
        pm = make_user(test_db, email="pm-wf16@interdec.com", role_names=["Accountable PM"])
        outsider = make_user(test_db, email="out-wf16@interdec.com")
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id), visibility_mode="private")
        stage = _stage(client, task["id"])

        client.get("/api/v1/auth/logout")
        login(client, "out-wf16@interdec.com", "Secret!1234")
        response = client.get(f"/api/v1/tasks/{task['id']}/workflow")
        assert response.status_code == 404
        response = client.post(f"/api/v1/tasks/{task['id']}/stages", json={"name": "Nope"})
        assert response.status_code == 404
        response = client.post(
            f"/api/v1/tasks/{task['id']}/stages/{stage['id']}/transition",
            json={"to_status": "in_progress"},
        )
        assert response.status_code == 404

    def test_view_grant_cannot_modify_workflow(self, client, test_db):
        pm = make_user(test_db, email="pm-wf17@interdec.com", role_names=["Accountable PM"])
        viewer = make_user(test_db, email="view-wf17@interdec.com")
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id), visibility_mode="custom",
                            grant_user_ids=[str(viewer.id)], grant_access_level="view")
        stage = _stage(client, task["id"])

        client.get("/api/v1/auth/logout")
        login(client, "view-wf17@interdec.com", "Secret!1234")
        response = client.get(f"/api/v1/tasks/{task['id']}/workflow")
        assert response.status_code == 200  # can read
        response = client.post(f"/api/v1/tasks/{task['id']}/stages", json={"name": "Nope"})
        assert response.status_code == 404  # cannot restructure
        response = client.post(
            f"/api/v1/tasks/{task['id']}/stages/{stage['id']}/transition",
            json={"to_status": "in_progress"},
        )
        assert response.status_code == 404  # cannot drive stages either

    def test_operate_grant_can_transition_items_but_not_restructure(self, client, test_db):
        pm = make_user(test_db, email="pm-wf18@interdec.com", role_names=["Accountable PM"])
        operator = make_user(test_db, email="op-wf18@interdec.com")
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id), visibility_mode="custom",
                            grant_user_ids=[str(operator.id)], grant_access_level="operate")
        stage = _stage(client, task["id"])
        item = _item(client, task["id"], stage["id"], "Operator work")
        _start_task(client, task["id"])

        client.get("/api/v1/auth/logout")
        login(client, "op-wf18@interdec.com", "Secret!1234")
        response = client.post(
            f"/api/v1/tasks/{task['id']}/items/{item['id']}/transition",
            json={"to_status": "in_progress"},
        )
        assert response.status_code == 200

        # Restructuring needs manage level.
        response = client.post(f"/api/v1/tasks/{task['id']}/stages", json={"name": "Nope"})
        assert response.status_code == 404
        response = client.post(
            f"/api/v1/tasks/{task['id']}/items/{item['id']}/assign",
            json={"assigned_user_id": str(operator.id)},
        )
        assert response.status_code == 404

    def test_cancel_item_needs_more_than_view(self, client, test_db):
        pm = make_user(test_db, email="pm-wf19@interdec.com", role_names=["Accountable PM"])
        operator = make_user(test_db, email="op-wf19@interdec.com")
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id), visibility_mode="custom",
                            grant_user_ids=[str(operator.id)], grant_access_level="operate")
        stage = _stage(client, task["id"])
        item = _item(client, task["id"], stage["id"], "To cancel")

        client.get("/api/v1/auth/logout")
        login(client, "op-wf19@interdec.com", "Secret!1234")
        response = client.post(
            f"/api/v1/tasks/{task['id']}/items/{item['id']}/transition",
            json={"to_status": "cancelled", "reason": "Scope cut"},
        )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Audit + activity
# ---------------------------------------------------------------------------

class TestWorkflowAuditTrail:
    def test_workflow_mutations_are_audited_and_visible(self, client, test_db):
        pm = make_user(test_db, email="pm-wf20@interdec.com", role_names=["Accountable PM"])
        employee = make_user(test_db, email="emp-wf20@interdec.com")
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        stage = _stage(client, task["id"], "Build")
        item = _item(client, task["id"], stage["id"], "Component")
        response = client.post(
            f"/api/v1/tasks/{task['id']}/items/{item['id']}/assign",
            json={"assigned_user_id": str(employee.id)},
        )
        assert response.status_code == 200, response.text
        client.post(f"/api/v1/tasks/{task['id']}/dependencies",
                    json={"predecessor_id": item["id"], "successor_id": item["id"]})  # 422 self
        _start_task(client, task["id"])
        client.post(f"/api/v1/tasks/{task['id']}/items/{item['id']}/transition",
                    json={"to_status": "in_progress"})
        client.post(f"/api/v1/tasks/{task['id']}/items/{item['id']}/transition",
                    json={"to_status": "completed"})

        activity = client.get(f"/api/v1/tasks/{task['id']}/activity").json()
        types = [a["activity_type"] for a in activity]
        assert "workflow.stage_created" in types
        assert "workflow.item_created" in types
        assert "workflow.item_assigned" in types
        assert "workflow.item_transitioned" in types

        from app.models import AuditEvent
        events = test_db.query(AuditEvent).filter(
            AuditEvent.action.like("workflow.%")
        ).all()
        actions = {e.action for e in events}
        assert {"workflow.stage_created", "workflow.item_created",
                "workflow.item_transitioned"} <= actions
        # The auto-completion check raised before any dependency was created;
        # ensure the failed self-dependency did NOT audit as added.
        assert "workflow.dependency_added" not in actions


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

class TestTemplatesAPI:
    def test_admin_can_manage_templates(self, client, test_db):
        login(client, "admin@interdec.com", "DecOps!2026")
        payload = {
            "name": "Standard rollout",
            "description": "Three-phase rollout",
            "stages": [
                {"name": "Prepare", "execution_mode": "sequential",
                 "items": [{"item_type": "subtask", "title": "Kickoff"}]},
                {"name": "Execute", "execution_mode": "parallel",
                 "items": [{"item_type": "milestone", "title": "Go live"}]},
            ],
        }
        response = client.post("/api/v1/workflow-templates", json=payload)
        assert response.status_code == 201, response.text
        template = response.json()
        assert template["definition"]["stages"][0]["name"] == "Prepare"

        listing = client.get("/api/v1/workflow-templates").json()
        assert listing["total"] == 1

        response = client.patch(
            f"/api/v1/workflow-templates/{template['id']}",
            json={"is_active": False},
        )
        assert response.status_code == 200
        listing = client.get("/api/v1/workflow-templates").json()
        assert listing["total"] == 0  # deactivated templates are hidden

    def test_non_admin_gets_404_on_templates(self, client, test_db):
        make_user(test_db, email="plain-tpl@interdec.com")  # Department Member
        login(client, "plain-tpl@interdec.com", "Secret!1234")
        response = client.get("/api/v1/workflow-templates")
        assert response.status_code == 404
        response = client.post("/api/v1/workflow-templates", json={
            "name": "Nope", "stages": [{"name": "S"}],
        })
        assert response.status_code == 404
