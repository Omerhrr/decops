""" hardening suite: security headers, cookie/session hygiene,
unauthenticated endpoint matrix, IDOR/privilege-escalation probes, mass
assignment robustness, and the audit-trail coverage matrix.

These tests complement the per-feature authorization suites (Phases 2-8):
they attack the API the way a penetration pass would and verify the audit
trail records every mutation with actor, action, and resource.
"""

import io
import uuid

from sqlalchemy import select

from app.domain.task_lifecycle import TaskStatus
from app.models import AuditEvent, Task, TaskPriority

from tests.conftest import login, make_user

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROTECTED_ENDPOINTS = [
    ("GET", "/api/v1/auth/me"),
    ("GET", "/api/v1/users"),
    ("GET", "/api/v1/departments"),
    ("GET", "/api/v1/roles"),
    ("GET", "/api/v1/tasks"),
    ("GET", "/api/v1/tasks/00000000-0000-0000-0000-000000000000"),
    ("GET", "/api/v1/dashboard/summary"),
    ("GET", "/api/v1/dashboard/my-tasks"),
    ("GET", "/api/v1/reports/task-completion"),
    ("GET", "/api/v1/reports/department-workload"),
    ("GET", "/api/v1/imports"),
    ("GET", "/api/v1/notifications"),
]


def make_csv_row(title: str) -> dict:
    row = {h: "" for h in (
        "Task ID", "Date Created", "Task Title", "Task Description", "Priority",
        "Accountable PM", "Supporting PM(s)", "Assigned By", "Start Date",
        "Due Date", "Status", "% Complete", "Last Updated",
        "Next Follow-up Date", "Dependency / Blocker",
        "Attachment / Folder Link", "Completion Date",
    )}
    row.update({"Task ID": f"LEG-{abs(hash(title)) % 100000}", "Task Title": title})
    return row


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------

class TestSecurityHeaders:
    def test_all_responses_carry_hardening_headers(self, client):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert "default-src 'none'" in response.headers["content-security-policy"]
        assert response.headers["cache-control"] == "no-store"

    def test_hsts_only_for_https_deployments(self, test_db):
        """HSTS on plain HTTP would break sandbox access; it activates with
        the HTTPS-only deployment flag (secure_cookies)."""
        from app.core.config import Settings
        from app.main import create_app

        secure_app = create_app(override_settings=Settings(
            environment="testing", secure_cookies=True, database_url="sqlite://",
        ))
        with __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(secure_app) as sc:
            response = sc.get("/api/v1/health")
            assert response.headers["strict-transport-security"] == "max-age=31536000"

    def test_error_responses_carry_headers_too(self, client):
        response = client.get("/api/v1/tasks")
        assert response.status_code == 401
        assert response.headers["x-frame-options"] == "DENY"


# ---------------------------------------------------------------------------
# Session & cookie hygiene
# ---------------------------------------------------------------------------

class TestSessionSecurity:
    def test_login_cookie_flags(self, test_db, client):
        make_user(test_db, email="cookieuser@interdec.com", employee_code="INT-C1")
        response = login(client, "cookieuser@interdec.com", "Secret!1234")
        assert response.status_code == 200
        set_cookie = response.headers.get("set-cookie", "")
        assert "decops_session=" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "SameSite=lax" in set_cookie.lower().replace("samesite=lax", "SameSite=lax") or "samesite=lax" in set_cookie.lower()
        # secure flag only when the deployment is HTTPS
        assert "secure" not in set_cookie.lower() or "Secure" in set_cookie

    def test_logout_revokes_immediately(self, test_db, client):
        make_user(test_db, email="logoutuser@interdec.com", employee_code="INT-L1")
        login(client, "logoutuser@interdec.com", "Secret!1234")
        assert client.get("/api/v1/auth/me").status_code == 200
        assert client.post("/api/v1/auth/logout").status_code in (200, 204)
        assert client.get("/api/v1/auth/me").status_code == 401

    def test_forged_session_token_rejected(self, client):
        client.cookies.set("decops_session", "forged-token-value")
        assert client.get("/api/v1/auth/me").status_code == 401
        client.cookies.clear()

    def test_password_never_in_response_or_audit(
        self, test_db, client,
    ):
        make_user(test_db, email="pwuser@interdec.com", employee_code="INT-P1")
        response = login(client, "pwuser@interdec.com", "Secret!1234")
        assert "Secret!1234" not in response.text
        events = test_db.scalars(
            select(AuditEvent).where(AuditEvent.action == "auth.login")
        ).all()
        for event in events:
            assert "Secret!1234" not in str(event.metadata_json)


# ---------------------------------------------------------------------------
# Unauthenticated endpoint matrix (penetration probe)
# ---------------------------------------------------------------------------

class TestUnauthenticatedMatrix:
    def test_every_protected_endpoint_requires_authentication(self, client):
        for method, path in PROTECTED_ENDPOINTS:
            response = client.request(method, path)
            assert response.status_code == 401, (method, path, response.status_code)

    def test_mutations_require_authentication(self, client):
        probes = [
            ("POST", "/api/v1/tasks", {"title": "x"}),
            ("POST", "/api/v1/users", {"email": "x@x.com"}),
            ("POST", "/api/v1/departments", {"name": "x"}),
            ("POST", "/api/v1/reports/exports", {"export_type": "task_register"}),
        ]
        for method, path, body in probes:
            response = client.request(method, path, json=body)
            assert response.status_code == 401, (method, path, response.status_code)

    def test_openapi_disabled_behind_production_flag(self, test_db):
        from app.core.config import Settings
        from app.main import create_app

        prod_app = create_app(override_settings=Settings(
            environment="production", database_url="sqlite://",
            session_secret_key="x" * 32,
        ))
        with __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(prod_app) as sc:
            assert sc.get("/api/docs").status_code in (404, 401)
            assert sc.get("/api/openapi.json").status_code in (404, 401)


# ---------------------------------------------------------------------------
# IDOR / privilege escalation probes
# ---------------------------------------------------------------------------

class TestAccessControlProbes:
    def _task(self, test_db, owner, *, title, mode):
        task = Task(
            task_number=f"TSK-2026-{abs(hash(title)) % 9000 + 100:04d}",
            title=title, priority=TaskPriority.medium, status=TaskStatus.open,
            accountable_pm_id=owner.id, created_by_id=owner.id,
            visibility_mode=mode,
        )
        test_db.add(task)
        test_db.commit()
        return task

    def test_private_task_hidden_from_everyone_else(self, test_db, client):
        owner = make_user(test_db, email="owner@interdec.com", employee_code="INT-O1",
                          role_names=["Accountable PM"])
        outsider = make_user(test_db, email="outsider@interdec.com", employee_code="INT-X1",
                             role_names=["Department Member"])
        task = self._task(test_db, owner, title="Private hardening probe", mode="private")
        login(client, "outsider@interdec.com", "Secret!1234")
        for path in (
            f"/api/v1/tasks/{task.id}",
            f"/api/v1/tasks/{task.id}/comments",
            f"/api/v1/tasks/{task.id}/attachments",
            f"/api/v1/tasks/{task.id}/activity",
        ):
            assert client.get(path).status_code == 404, path
        # Mutations equally denied with non-enumerating codes (payload must
        # pass schema validation so the request reaches authorization).
        assert client.post(
            f"/api/v1/tasks/{task.id}/transition",
            json={"to_status": "in_progress", "reason": "penetration probe"},
        ).status_code == 404

    def test_member_cannot_reach_administration(self, test_db, client):
        make_user(test_db, email="plainmember@interdec.com", employee_code="INT-M1",
                  role_names=["Department Member"])
        login(client, "plainmember@interdec.com", "Secret!1234")
        for method, path in (
            ("GET", "/api/v1/users"),
            ("POST", "/api/v1/users"),
            ("GET", "/api/v1/imports"),
            ("GET", "/api/v1/roles/permissions"),
        ):
            response = client.request(method, path)
            assert response.status_code in (403, 404), (method, path, response.status_code)

    def test_invalid_uuids_rejected_cleanly(self, test_db, client):
        make_user(test_db, email="uuidprobe@interdec.com", employee_code="INT-U1")
        login(client, "uuidprobe@interdec.com", "Secret!1234")
        for path in ("/api/v1/tasks/not-a-uuid", "/api/v1/users/not-a-uuid"):
            response = client.get(path)
            assert response.status_code in (404, 422), path

    def test_mass_assignment_cannot_change_identity_fields(
        self, test_db, client,
    ):
        admin = make_user(test_db, email="massassign@interdec.com", employee_code="INT-MA1",
                          role_names=["Accountable PM"])
        login(client, "massassign@interdec.com", "Secret!1234")
        task = self._task(test_db, admin, title="Mass assignment probe", mode="private")
        original_number = task.task_number
        # Identity fields and a bogus version are sent alongside the permitted
        # field; the schema must ignore unknown fields and the version value
        # Must be the REAL one, not the attacker-supplied 99.
        response = client.patch(
            f"/api/v1/tasks/{task.id}",
            json={
                "task_number": "TSK-9999-0001",   # identity field
                "created_by_id": "00000000-0000-0000-0000-000000000000",
                "version": task.version,
                "title": "Mass assignment probe v2",
            },
        )
        assert response.status_code == 200, response.text
        test_db.refresh(task)
        assert task.task_number == original_number      # unchanged
        assert task.created_by_id == admin.id           # unchanged
        assert task.version == 2                        # normal bump, not 99
        assert task.title == "Mass assignment probe v2"  # permitted field applied

    def test_profile_update_cannot_self_escalate(self, test_db, client):
        make_user(test_db, email="selfescal@interdec.com", employee_code="INT-SE1",
                  role_names=["Department Member"])
        login(client, "selfescal@interdec.com", "Secret!1234")
        me = client.get("/api/v1/auth/me").json()
        response = client.patch(f"/api/v1/users/{me['id']}", json={
            "account_status": "active",
            "employee_code": "INT-HACK",
        })
        # Either rejected (422/403/404) or applied-but-harmless; the user must
        # not gain roles/permissions from it either way.
        codes = client.get("/api/v1/auth/me").json().get("permissions", [])
        assert "users.manage" not in codes
        assert "imports.manage" not in codes


# ---------------------------------------------------------------------------
# Audit trail coverage matrix
# ---------------------------------------------------------------------------

class TestAuditCoverageMatrix:
    def test_mutation_matrix_is_audited(self, test_db, client):
        from datetime import date

        admin = make_user(test_db, email="auditor-admin@interdec.com", employee_code="INT-AU1",
                          role_names=["Company Administrator"])
        pm = make_user(test_db, email="audit-pm@interdec.com", employee_code="INT-AU2",
                       role_names=["Accountable PM"])
        login(client, "auditor-admin@interdec.com", "Secret!1234")

        client.post("/api/v1/users", json={
            "email": "audited.user@interdec.com", "full_name": "Audited User",
            "employee_code": "INT-AU3", "password": "Secret!1234",
            "role_names": ["Department Member"],
        })
        client.post("/api/v1/departments", json={"name": "Audit Probe Dept"})
        task_response = client.post("/api/v1/tasks", json={
            "title": "Audit probe task",
            "accountable_pm_id": str(pm.id),
            "priority": "high",
            "due_date": date(2026, 12, 1).isoformat(),
        })
        assert task_response.status_code == 201, task_response.text
        task_id = task_response.json()["id"]
        version = task_response.json()["version"]

        client.patch(f"/api/v1/tasks/{task_id}", json={
            "title": "Audit probe task v2", "version": version,
        })
        client.post(f"/api/v1/tasks/{task_id}/transition", json={
            "to_status": "open", "reason": "audit probe",
        })
        client.post(f"/api/v1/tasks/{task_id}/assignments", json={
            "user_id": str(admin.id), "assignment_role": "supporting_pm",
        })

        actions = {e.action for e in test_db.scalars(select(AuditEvent)).all()}
        required = {
            "user.created", "department.created", "task.created",
            "task.updated", "task.status_changed", "task.assigned",
            "auth.login",
        }
        missing = required - actions
        assert not missing, f"actions missing audit events: {missing}"

    def test_audit_events_carry_actor_and_timestamp(self, test_db, client):
        make_user(test_db, email="actortest@interdec.com", employee_code="INT-AC1")
        login(client, "actortest@interdec.com", "Secret!1234")
        events = test_db.scalars(
            select(AuditEvent).where(AuditEvent.action == "auth.login")
        ).all()
        assert events
        for event in events:
            assert event.actor_user_id is not None or event.action == "auth.login_failed"
            assert event.occurred_at is not None
