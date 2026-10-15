"""Phase 7 — Reporting & export tests (MOD-007 + MOD-005 "Restricted exports").

Under test:
- reports.view gates task-completion (Management).
- reports.department.view scopes department workload to the lead's own
  departments; reports.view sees all departments.
- exports.approved gates CSV exports; exported rows re-pass the access
  engine, so restricted tasks never appear; exports are audited; CSV cells
  are formula-injection sanitized.
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.models import (
    AuditEvent,
    Department,
    DepartmentMembership,
    MembershipRole,
    Task,
    User,
    WorkItem,
    WorkItemType,
)
from tests.conftest import login, make_user


def _create_task(client: TestClient, *, pm_id: str, **overrides) -> dict:
    payload = {
        "title": "Report reconciliation effort",
        "priority": "high",
        "accountable_pm_id": pm_id,
        "due_date": "2030-06-30",
        "visibility_mode": "participants",
    }
    payload.update(overrides)
    response = client.post("/api/v1/tasks", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _dept(db, name: str, lead: User | None = None) -> Department:
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


class TestTaskCompletionReport:
    def test_requires_reports_view(self, client, test_db):
        make_user(test_db, email="completionember@interdec.com", role_names=["Department Member"])
        make_user(test_db, email="completionmgr@interdec.com", role_names=["Management"])

        login(client, "completionember@interdec.com", "Secret!1234")
        assert client.get("/api/v1/reports/task-completion").status_code == 404

        login(client, "completionmgr@interdec.com", "Secret!1234")
        response = client.get("/api/v1/reports/task-completion")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["totals"]["visible_total"] == 0  # no tasks visible yet
        assert len(body["series"]) == 12  # default window

    def test_completion_counts_only_visible_tasks(self, client, test_db):
        # Admin creates/operates; a Management viewer (reports.view) gets an
        # explicit view grant — reports aggregate exactly the authorized set.
        manager = make_user(test_db, email="completiomgr@interdec.com", role_names=["Management"])
        pm = make_user(test_db, email="completiopm@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")

        task = _create_task(client, pm_id=str(pm.id))
        client.post(f"/api/v1/tasks/{task['id']}/access-grants",
                    json={"user_id": str(manager.id), "access_level": "view"})
        for status in ("open", "in_progress", "completed"):
            reason = {"open": "kick off", "in_progress": "wip", "completed": "done"}[status]
            response = client.post(f"/api/v1/tasks/{task['id']}/transition",
                                   json={"to_status": status, "reason": reason})
            assert response.status_code == 200, response.text

        # The granted manager sees the completed task in their window.
        login(client, "completiomgr@interdec.com", "Secret!1234")
        body = client.get("/api/v1/reports/task-completion?weeks=4").json()
        current_week = body["series"][-1]
        assert current_week["completed"] == 1
        assert current_week["created"] == 1
        assert body["totals"]["completed_in_window"] == 1
        assert body["avg_days_to_complete"] is not None

        # A manager without the grant does not see it at all.
        outsider = make_user(test_db, email="completioout@interdec.com", role_names=["Management"])
        login(client, "completioout@interdec.com", "Secret!1234")
        other = client.get("/api/v1/reports/task-completion?weeks=4").json()
        assert other["totals"]["visible_total"] == 0
        assert sum(p["completed"] for p in other["series"]) == 0

    def test_milestone_progress_and_blocker_analysis(self, client, test_db):
        manager = make_user(test_db, email="milestonemgr@interdec.com", role_names=["Management"])
        pm = make_user(test_db, email="milestonepm@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id), title="Milestone probe")
        client.post(f"/api/v1/tasks/{task['id']}/access-grants",
                    json={"user_id": str(manager.id), "access_level": "view"})
        client.post(f"/api/v1/tasks/{task['id']}/transition",
                    json={"to_status": "open", "reason": "kick off"})

        # One stage, one milestone.
        response = client.post(f"/api/v1/tasks/{task['id']}/stages",
                               json={"name": "Discovery", "execution_mode": "sequential"})
        assert response.status_code == 201, response.text
        stage_id = response.json()["id"]
        response = client.post(f"/api/v1/tasks/{task['id']}/stages/{stage_id}/items",
                               json={"item_type": "milestone", "title": "Kickoff milestone"})
        milestone_id = response.json()["id"]

        # The granted manager reads the report (admin holds no reports.view).
        login(client, "milestonemgr@interdec.com", "Secret!1234")
        body = client.get("/api/v1/reports/task-completion").json()
        assert body["milestone_progress"]["total"] == 1
        assert body["milestone_progress"]["pending"] == 1
        # Complete the milestone via transition (task must be in progress).
        login(client, "admin@interdec.com", "DecOps!2026")
        client.post(f"/api/v1/tasks/{task['id']}/transition",
                    json={"to_status": "in_progress", "reason": "wip"})
        response = client.post(
            f"/api/v1/tasks/{task['id']}/items/{milestone_id}/transition",
            json={"to_status": "in_progress"})
        assert response.status_code == 200, response.text
        client.post(f"/api/v1/tasks/{task['id']}/items/{milestone_id}/transition",
                    json={"to_status": "completed"})
        login(client, "milestonemgr@interdec.com", "Secret!1234")
        body = client.get("/api/v1/reports/task-completion").json()
        assert body["milestone_progress"]["completed"] == 1

        # Block the task (admin operates); blocker analysis picks it up.
        login(client, "admin@interdec.com", "DecOps!2026")
        client.post(f"/api/v1/tasks/{task['id']}/transition",
                    json={"to_status": "blocked", "reason": "vendor outage"})
        login(client, "milestonemgr@interdec.com", "Secret!1234")
        body = client.get("/api/v1/reports/task-completion").json()
        assert body["blocker_analysis"]["blocked_total"] == 1
        assert body["blocker_analysis"]["by_priority"].get("high") == 1


class TestDepartmentWorkload:
    def test_management_sees_all_lead_sees_own(self, client, test_db):
        admin = test_db.query(User).filter_by(email="admin@interdec.com").first()
        lead_a = make_user(test_db, email="wkleada@interdec.com", role_names=["Department Lead"])
        lead_b = make_user(test_db, email="wkleadb@interdec.com", role_names=["Department Lead"])
        dept_a = _dept(test_db, "Ops Alpha", lead=lead_a)
        _dept(test_db, "Ops Beta", lead=lead_b)
        pm = make_user(test_db, email="wklopm@interdec.com", role_names=["Accountable PM"])

        login(client, "admin@interdec.com", "DecOps!2026")
        _create_task(client, pm_id=str(pm.id), title="Alpha scoped effort",
                     visibility_mode="department_scoped", department_ids=[str(dept_a.id)])

        # Management: all departments (their own visible set: none of the
        # dept-scoped task because Management lacks view_department).
        manager = make_user(test_db, email="wklomgr@interdec.com", role_names=["Management"])
        login(client, "wklomgr@interdec.com", "Secret!1234")
        body = client.get("/api/v1/reports/department-workload").json()
        assert body["scope"] == "all"
        assert {d["department_name"] for d in body["departments"]} == {"Ops Alpha", "Ops Beta"}
        alpha = next(d for d in body["departments"] if d["department_name"] == "Ops Alpha")
        assert alpha["active_tasks"] == 0  # management cannot view dept-scoped task
        assert alpha["member_count"] == 1

        # Lead A: only their department, and the dept task is visible to them.
        login(client, "wkleada@interdec.com", "Secret!1234")
        body = client.get("/api/v1/reports/department-workload").json()
        assert body["scope"] == "my_departments"
        assert [d["department_name"] for d in body["departments"]] == ["Ops Alpha"]
        assert body["departments"][0]["active_tasks"] == 1

        # Lead B sees their (empty) department only — no Alpha row at all.
        login(client, "wkleadb@interdec.com", "Secret!1234")
        body = client.get("/api/v1/reports/department-workload").json()
        assert [d["department_name"] for d in body["departments"]] == ["Ops Beta"]

        # Members hold neither report permission.
        member = make_user(test_db, email="wklomem@interdec.com", role_names=["Department Member"])
        login(client, "wklomem@interdec.com", "Secret!1234")
        assert client.get("/api/v1/reports/department-workload").status_code == 404

    def test_private_task_not_counted_for_lead(self, client, test_db):
        admin = test_db.query(User).filter_by(email="admin@interdec.com").first()
        lead = make_user(test_db, email="wkleadc@interdec.com", role_names=["Department Lead"])
        dept = _dept(test_db, "Ops Gamma", lead=lead)
        pm = make_user(test_db, email="wklcpm@interdec.com", role_names=["Accountable PM"])

        login(client, "admin@interdec.com", "DecOps!2026")
        # Private task linked to the dept: the lead has no participants circle.
        _create_task(client, pm_id=str(pm.id), title="Private gamma probe",
                     visibility_mode="private", department_ids=[str(dept.id)])
        _create_task(client, pm_id=str(pm.id), title="Scoped gamma probe",
                     visibility_mode="department_scoped", department_ids=[str(dept.id)])

        login(client, "wkleadc@interdec.com", "Secret!1234")
        body = client.get("/api/v1/reports/department-workload").json()
        gamma = body["departments"][0]
        assert gamma["active_tasks"] == 1  # only the department-scoped task


class TestExports:
    def test_exports_require_exports_approved(self, client, test_db):
        make_user(test_db, email="exportmgr@interdec.com", role_names=["Management"])
        make_user(test_db, email="exportaud@interdec.com", role_names=["Read-Only Auditor"])

        login(client, "exportmgr@interdec.com", "Secret!1234")
        assert client.post("/api/v1/reports/exports",
                           json={"export_type": "task_register"}).status_code == 404

        login(client, "exportaud@interdec.com", "Secret!1234")
        response = client.post("/api/v1/reports/exports", json={"export_type": "task_register"})
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert "decops_task_register_" in response.headers["content-disposition"]

    def test_export_rows_are_authorization_filtered(self, client, test_db):
        admin = test_db.query(User).filter_by(email="admin@interdec.com").first()
        pm = make_user(test_db, email="expfpm@interdec.com", role_names=["Accountable PM"])
        auditor = make_user(test_db, email="expfaud@interdec.com", role_names=["Read-Only Auditor"])

        login(client, "admin@interdec.com", "DecOps!2026")
        visible_task = _create_task(client, pm_id=str(pm.id), title="Exportable effort")
        _create_task(client, pm_id=str(pm.id), title="Hidden secret effort",
                     visibility_mode="private")
        # Grant the auditor view on one task only.
        response = client.post(f"/api/v1/tasks/{visible_task['id']}/access-grants",
                               json={"user_id": str(auditor.id), "access_level": "view"})
        assert response.status_code == 201, response.text

        login(client, "expfaud@interdec.com", "Secret!1234")
        response = client.post("/api/v1/reports/exports", json={"export_type": "task_register"})
        assert response.status_code == 200
        assert "Exportable effort" in response.text
        assert "Hidden secret effort" not in response.text

    def test_export_csv_formula_injection_sanitized(self, client, test_db):
        admin = test_db.query(User).filter_by(email="admin@interdec.com").first()
        pm = make_user(test_db, email="expspm@interdec.com", role_names=["Accountable PM"])
        auditor = make_user(test_db, email="expsaud@interdec.com", role_names=["Read-Only Auditor"])

        evil_title = "=HYPERLINK(\"http://evil.example\",\"pwn\")"
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id), title=evil_title)
        client.post(f"/api/v1/tasks/{task['id']}/access-grants",
                    json={"user_id": str(auditor.id), "access_level": "view"})

        login(client, "expsaud@interdec.com", "Secret!1234")
        response = client.post("/api/v1/reports/exports", json={"export_type": "task_register"})
        assert response.status_code == 200
        # The dangerous leading '=' must be neutralized in the cell.
        assert "'=HYPERLINK" in response.text
        assert "\n=HYPERLINK" not in response.text

    def test_export_filters_and_status(self, client, test_db):
        admin = test_db.query(User).filter_by(email="admin@interdec.com").first()
        pm = make_user(test_db, email="expftpm@interdec.com", role_names=["Accountable PM"])
        auditor = make_user(test_db, email="expftaud@interdec.com", role_names=["Read-Only Auditor"])
        # Auditor as participant on both tasks (simplest authorized view).
        login(client, "admin@interdec.com", "DecOps!2026")
        t1 = _create_task(client, pm_id=str(pm.id), title="Draft register row")
        t2 = _create_task(client, pm_id=str(pm.id), title="Open register row")
        client.post(f"/api/v1/tasks/{t2['id']}/transition",
                    json={"to_status": "open", "reason": "kick off"})
        for t in (t1, t2):
            client.post(f"/api/v1/tasks/{t['id']}/access-grants",
                        json={"user_id": str(auditor.id), "access_level": "view"})

        login(client, "expftaud@interdec.com", "Secret!1234")
        response = client.post("/api/v1/reports/exports",
                               json={"export_type": "task_register", "status": "draft"})
        rows = [line for line in response.text.strip().splitlines()[1:] if line]
        assert len(rows) == 1
        assert "Draft register row" in rows[0]

        response = client.post("/api/v1/reports/exports",
                               json={"export_type": "task_register", "status": "completed"})
        rows = [line for line in response.text.strip().splitlines()[1:] if line]
        assert rows == []

    def test_exports_are_audited(self, client, test_db):
        make_user(test_db, email="expaaud@interdec.com", role_names=["Read-Only Auditor"])
        login(client, "expaaud@interdec.com", "Secret!1234")
        response = client.post("/api/v1/reports/exports", json={"export_type": "department_workload"})
        assert response.status_code == 200
        events = test_db.query(AuditEvent).filter_by(action="report.exported").all()
        assert len(events) == 1
        assert events[0].metadata_json["export_type"] == "department_workload"
        # The auditor holds no reports.view: scoped to their (empty) departments.
        assert "0 row(s)" in events[0].change_summary


class TestDepartmentWorkspace:
    def test_workspace_payload_is_engine_filtered(self, client, test_db):
        admin = test_db.query(User).filter_by(email="admin@interdec.com").first()
        lead = make_user(test_db, email="wslead@interdec.com", role_names=["Department Lead"])
        member = make_user(test_db, email="wsmember@interdec.com", role_names=["Department Member"])
        dept = _dept(test_db, "Workspace Ops", lead=lead)
        dept.memberships.append(DepartmentMembership(department_id=dept.id, user_id=member.id))
        test_db.commit()
        pm = make_user(test_db, email="wspmpm@interdec.com", role_names=["Accountable PM"])

        login(client, "admin@interdec.com", "DecOps!2026")
        soon = (datetime.now(UTC) + timedelta(days=5)).date().isoformat()
        scoped = _create_task(client, pm_id=str(pm.id), title="Workspace scoped effort",
                              visibility_mode="department_scoped",
                              department_ids=[str(dept.id)], due_date=soon)
        _create_task(client, pm_id=str(pm.id), title="Workspace hidden effort",
                     visibility_mode="private", department_ids=[str(dept.id)])
        client.post(f"/api/v1/tasks/{scoped['id']}/grants",
                    json={"user_id": str(member.id), "access_level": "operate"})

        login(client, "wslead@interdec.com", "Secret!1234")
        response = client.get(f"/api/v1/reports/departments/{dept.id}/workspace")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["department"]["name"] == "Workspace Ops"
        titles = [t["title"] for t in body["tasks"]]
        assert "Workspace scoped effort" in titles
        assert "Workspace hidden effort" not in titles
        assert body["active_total"] == 1
        assert len(body["upcoming"]) == 1
        team_ids = {u["user"]["id"] for u in body["team"]}
        assert str(member.id) in team_ids and str(lead.id) in team_ids

        # Unknown department -> 404.
        response = client.get(f"/api/v1/reports/departments/{uuid.uuid4()}/workspace")
        assert response.status_code == 404
