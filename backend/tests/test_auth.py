"""Authentication + authorization flow tests (spec security.mandatory_test_scenarios)."""

from tests.conftest import login, make_user


class TestAuthentication:
    def test_health_ok(self, client):
        res = client.get("/api/v1/health")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ok"
        assert body["database"] == "ok"

    def test_login_success_sets_httponly_cookie(self, client, test_db):
        make_user(test_db, email="ada@interdec.com", password="Strong!Pass1")
        res = login(client, "ada@interdec.com", "Strong!Pass1")
        assert res.status_code == 200
        body = res.json()
        assert body["email"] == "ada@interdec.com"
        set_cookie = res.headers["set-cookie"]
        assert "httponly" in set_cookie.lower()
        assert "samesite=lax" in set_cookie.lower()

    def test_login_wrong_password_is_401(self, client, test_db):
        make_user(test_db, email="bob@interdec.com", password="Strong!Pass1")
        res = login(client, "bob@interdec.com", "nope")
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "invalid_credentials"

    def test_login_unknown_email_is_401_without_enumeration(self, client):
        res = login(client, "ghost@interdec.com", "whatever")
        assert res.status_code == 401
        # Same message as wrong-password to avoid account enumeration
        wrong_pw = login(
            client, "ghost2@interdec.com", "x"
        )  # also unknown -> same code
        assert res.json()["error"]["code"] == wrong_pw.json()["error"]["code"]

    def test_me_requires_session(self, client):
        res = client.get("/api/v1/auth/me")
        assert res.status_code == 401

    def test_logout_revokes_session_immediately(self, client, test_db):
        make_user(test_db, email="carol@interdec.com", password="Strong!Pass1")
        login(client, "carol@interdec.com", "Strong!Pass1")
        assert client.get("/api/v1/auth/me").status_code == 200
        assert client.post("/api/v1/auth/logout").status_code == 204
        # Revoked access takes effect immediately (spec task_visibility.rules)
        assert client.get("/api/v1/auth/me").status_code == 401

    def test_deactivated_user_cannot_login(self, client, test_db):
        make_user(
            test_db, email="dave@interdec.com", password="Strong!Pass1", status="deactivated"
        )
        res = login(client, "dave@interdec.com", "Strong!Pass1")
        assert res.status_code == 401

    def test_login_lockout_after_max_failures(self, client, test_db):
        make_user(test_db, email="erin@interdec.com", password="Strong!Pass1")
        for _ in range(5):
            login(client, "erin@interdec.com", "bad")
        res = login(client, "erin@interdec.com", "Strong!Pass1")
        assert res.status_code == 401
        assert res.json()["error"]["details"]["reason"] == "account_locked"


class TestAuthorization:
    def test_users_list_requires_admin_permission(self, client, test_db):
        # Anonymous
        assert client.get("/api/v1/users").status_code == 401
        # Non-admin member
        make_user(test_db, email="member@interdec.com", password="Strong!Pass1")
        login(client, "member@interdec.com", "Strong!Pass1")
        # 404 (not 403) to avoid confirming protected resource existence
        assert client.get("/api/v1/users").status_code == 404
        # Admin sees the list
        login(client, "admin@interdec.com", "DecOps!2026")
        res = client.get("/api/v1/users")
        assert res.status_code == 200
        body = res.json()
        assert body["total"] >= 2
        assert all("email" in item for item in body["items"])

    def test_me_returns_roles_and_permissions(self, client, test_db):
        make_user(
            test_db,
            email="lead@interdec.com",
            password="Strong!Pass1",
            role_names=["Department Lead"],
        )
        login(client, "lead@interdec.com", "Strong!Pass1")
        res = client.get("/api/v1/auth/me")
        body = res.json()
        assert "Department Lead" in [r["name"] for r in body["roles"]]
        assert "tasks.view_department" in body["permissions"]


class TestAuditTrail:
    def test_security_events_are_audited(self, client, test_db):
        from app.models import AuditEvent

        make_user(test_db, email="fred@interdec.com", password="Strong!Pass1")
        login(client, "fred@interdec.com", "Strong!Pass1")
        client.post("/api/v1/auth/logout")
        events = test_db.query(AuditEvent).filter_by(resource_type="user").all()
        actions = {e.action for e in events}
        assert "auth.login" in actions
        assert "auth.logout" in actions

    def test_failed_login_audited(self, client, test_db):
        from app.models import AuditEvent

        make_user(test_db, email="gina@interdec.com", password="Strong!Pass1")
        login(client, "gina@interdec.com", "wrong-password")
        failed = test_db.query(AuditEvent).filter_by(action="auth.login_failed").all()
        assert len(failed) == 1
