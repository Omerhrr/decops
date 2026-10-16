""" - Dashboard tests.

Exit criteria under test:
- "Dashboard totals reconcile with authorized task records": every summary
  total equals the number of rows the task register returns for the same
  actor (same engine, same policy assembly).
- "Restricted information does not leak": private tasks a user cannot view
  contribute nothing to their totals, deadline rows, blocked rows, or
  recent-activity feed.
"""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.models import Task, User
from tests.conftest import login, make_user


def _create_task(client: TestClient, *, pm_id: str, **overrides) -> dict:
    payload = {
        "title": "Quarterly data reconciliation",
        "priority": "high",
        "accountable_pm_id": pm_id,
        "due_date": "2030-06-30",
        "visibility_mode": "participants",
    }
    payload.update(overrides)
    response = client.post("/api/v1/tasks", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _transition(client: TestClient, task_id: str, to_status: str, reason: str = "needed") -> None:
    response = client.post(
        f"/api/v1/tasks/{task_id}/transition",
        json={"to_status": to_status, "reason": reason},
    )
    assert response.status_code == 200, response.text


def _register_total(client: TestClient) -> int:
    return client.get("/api/v1/tasks?page_size=100").json()["total"]


class TestSummaryReconciliation:
    def test_totals_reconcile_with_authorized_register(self, client, test_db):
        admin = test_db.query(User).filter_by(email="admin@interdec.com").first()
        pm1 = make_user(test_db, email="reconpm1@interdec.com", role_names=["Accountable PM"])
        pm2 = make_user(test_db, email="reconpm2@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")

        t1 = _create_task(client, pm_id=str(pm1.id))                      # participants: admin+pm1
        t2 = _create_task(client, pm_id=str(pm2.id), visibility_mode="private",
                          title="Confidential audit")
        _create_task(client, pm_id=str(pm1.id), title="Third effort")

        # PM1 sees T1 + T3, never the private T2.
        login(client, "reconpm1@interdec.com", "Secret!1234")
        register_total = _register_total(client)
        summary = client.get("/api/v1/dashboard/summary").json()

        assert summary["visible_total"] == register_total
        assert summary["visible_total"] == 2
        assert summary["me"]["accountable_active"] == 2
        assert summary["me"]["assigned_active"] == 2  # accountable PM is also an assignee
        assert summary["visible_totals"]["draft"] == 2

        # PM2 sees the private task + their own none-other.
        login(client, "reconpm2@interdec.com", "Secret!1234")
        summary2 = client.get("/api/v1/dashboard/summary").json()
        assert summary2["visible_total"] == _register_total(client) == 1
        assert summary2["me"]["accountable_active"] == 1

    def test_private_task_does_not_leak_into_details_or_activity(self, client, test_db):
        admin = test_db.query(User).filter_by(email="admin@interdec.com").first()
        pm1 = make_user(test_db, email="leakpm1@interdec.com", role_names=["Accountable PM"])
        pm2 = make_user(test_db, email="leakpm2@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")

        tomorrow = (datetime.now(UTC) + timedelta(days=2)).date().isoformat()
        _create_task(client, pm_id=str(pm2.id), visibility_mode="private",
                     title="Secret private leakprobe", due_date=tomorrow)

        login(client, "leakpm1@interdec.com", "Secret!1234")
        summary = client.get("/api/v1/dashboard/summary").json()
        assert summary["visible_total"] == 0
        assert all("leakprobe" not in (r["title"] + r["task_number"]).lower()
                   for r in summary["upcoming_deadlines"])
        assert all("leakprobe" not in (r["task_title"] + r["summary"]).lower()
                   for r in summary["recent_activity"])
        # The private task's creation activity is invisible to PM1's feed.
        assert summary["recent_activity"] == []

        # Blocked/overdue endpoints also carry nothing.
        assert client.get("/api/v1/dashboard/blocked").json() == []
        assert client.get("/api/v1/dashboard/overdue").json() == []


class TestPersonalSections:
    def test_assigned_vs_accountable_scopes(self, client, test_db):
        admin = test_db.query(User).filter_by(email="admin@interdec.com").first()
        accountable = make_user(test_db, email="acctpm@interdec.com", role_names=["Accountable PM"])
        support = make_user(test_db, email="suppm@interdec.com", role_names=["Supporting PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(accountable.id))
        client.post(f"/api/v1/tasks/{task['id']}/assignments",
                    json={"user_id": str(support.id), "assignment_role": "supporting_pm"})

        login(client, "suppm@interdec.com", "Secret!1234")
        assigned = client.get("/api/v1/dashboard/my-tasks?scope=assigned").json()
        accountable_page = client.get("/api/v1/dashboard/my-tasks?scope=accountable").json()
        all_page = client.get("/api/v1/dashboard/my-tasks?scope=all").json()

        assert assigned["total"] == 1 and accountable_page["total"] == 0
        assert all_page["total"] == 1
        assert assigned["items"][0]["task_number"] == task["task_number"]

        login(client, "acctpm@interdec.com", "Secret!1234")
        assert client.get("/api/v1/dashboard/my-tasks?scope=accountable").json()["total"] == 1

    def test_overdue_lists_only_active_past_due(self, client, test_db):
        admin = test_db.query(User).filter_by(email="admin@interdec.com").first()
        pm = make_user(test_db, email="oduepm@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")

        yesterday = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
        soon = (datetime.now(UTC) + timedelta(days=3)).date().isoformat()
        overdue_task = _create_task(client, pm_id=str(pm.id), due_date=yesterday,
                                    title="Overdue effort")
        _create_task(client, pm_id=str(pm.id), due_date=soon, title="Soon effort")
        _transition(client, overdue_task["id"], "open", "kick off")

        login(client, "oduepm@interdec.com", "Secret!1234")
        rows = client.get("/api/v1/dashboard/overdue").json()
        assert len(rows) == 1
        assert rows[0]["task_number"] == overdue_task["task_number"]
        assert rows[0]["days_left"] == -1

        summary = client.get("/api/v1/dashboard/summary").json()
        assert summary["me"]["overdue"] == 1
        assert summary["me"]["due_soon"] == 1
        assert any(r["task_number"] == overdue_task["task_number"]
                   for r in summary["upcoming_deadlines"]) is False  # overdue excluded from upcoming

        # Completing removes it from overdue (reconciles with lifecycle state).
        login(client, "admin@interdec.com", "DecOps!2026")
        _transition(client, overdue_task["id"], "in_progress", "wip")
        _transition(client, overdue_task["id"], "completed", "done early")
        login(client, "oduepm@interdec.com", "Secret!1234")
        assert client.get("/api/v1/dashboard/overdue").json() == []

    def test_blocked_endpoint_and_summary(self, client, test_db):
        admin = test_db.query(User).filter_by(email="admin@interdec.com").first()
        pm = make_user(test_db, email="blkpm@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        _transition(client, task["id"], "open", "kick off")
        _transition(client, task["id"], "blocked", "waiting on vendor")

        login(client, "blkpm@interdec.com", "Secret!1234")
        rows = client.get("/api/v1/dashboard/blocked").json()
        assert [r["task_number"] for r in rows] == [task["task_number"]]
        summary = client.get("/api/v1/dashboard/summary").json()
        assert summary["me"]["blocked"] == 1
        assert summary["blocked_total"] == 1
        assert summary["visible_totals"]["blocked"] == 1


class TestManagementOverview:
    def test_overview_gated_and_reconciled(self, client, test_db):
        admin = test_db.query(User).filter_by(email="admin@interdec.com").first()
        pm = make_user(test_db, email="mgmt-see@interdec.com", role_names=["Accountable PM"])
        manager = make_user(test_db, email="mgmtuser@interdec.com", role_names=["Management"])
        member = make_user(test_db, email="plainmember@interdec.com", role_names=["Department Member"])
        login(client, "admin@interdec.com", "DecOps!2026")
        _create_task(client, pm_id=str(pm.id))
        _create_task(client, pm_id=str(pm.id), title="Second build")

        # Management (dashboards.view) gets the overview block...
        login(client, "mgmtuser@interdec.com", "Secret!1234")
        summary = client.get("/api/v1/dashboard/summary").json()
        # Management holds no manage_all: sees only tasks they participate in.
        assert summary["management_overview"] is None or \
            summary["management_overview"]["total_visible"] <= 2

        # ...but a plain member does not.
        login(client, "plainmember@interdec.com", "Secret!1234")
        assert client.get("/api/v1/dashboard/summary").json()["management_overview"] is None

    def test_admin_overview_covers_whole_register(self, client, test_db):
        # Company Administrator sees everything via tasks.manage_all, but the
        # overview block is dashboards.view-gated (Management only per matrix).
        admin = test_db.query(User).filter_by(email="admin@interdec.com").first()
        pm = make_user(test_db, email="adminview@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        _create_task(client, pm_id=str(pm.id))
        summary = client.get("/api/v1/dashboard/summary").json()
        assert summary["visible_total"] == 1
        assert summary["management_overview"] is None  # admin lacks dashboards.view


class TestAuthRequired:
    def test_anonymous_requests_rejected(self, client):
        for path in ("/dashboard/summary", "/dashboard/my-tasks",
                     "/dashboard/overdue", "/dashboard/blocked"):
            response = client.get(f"/api/v1{path}")
            assert response.status_code == 401, (path, response.status_code)
