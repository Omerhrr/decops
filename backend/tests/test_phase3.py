"""Phase 3: API tokens, webhooks, recurring tasks, timezone preference."""

from datetime import date, timedelta

import pytest

from app.models import RecurringTask, Task, User
from app.services import recurrence_service, webhook_service
from tests.conftest import login, make_user

ADMIN = ("admin@interdec.com", "DecOps!2026")


def _make_token(client, **kw):
    r = client.post("/api/v1/integrations/api-tokens", json={"name": "ci", **kw})
    assert r.status_code == 201, r.text
    return r.json()


class TestApiTokens:
    def test_token_authenticates_and_is_read_only_by_default(self, client, test_db):
        login(client, *ADMIN)
        tok = _make_token(client)["token"]
        client.cookies.clear()
        h = {"Authorization": f"Bearer {tok}"}
        assert client.get("/api/v1/tasks", headers=h).status_code == 200
        assert client.post("/api/v1/saved-filters", headers=h, json={"name": "x", "params": {}}).status_code == 404

    def test_token_cannot_reach_account_security_or_manage_tokens(self, client, test_db):
        login(client, *ADMIN)
        tok = _make_token(client, scope="write")["token"]
        client.cookies.clear()
        h = {"Authorization": f"Bearer {tok}"}
        assert client.get("/api/v1/auth/sessions", headers=h).status_code == 404
        assert client.get("/api/v1/integrations/api-tokens", headers=h).status_code == 404

    def test_revoked_and_unknown_tokens_rejected(self, client, test_db):
        login(client, *ADMIN)
        created = _make_token(client)
        assert client.delete(f"/api/v1/integrations/api-tokens/{created['id']}").status_code == 204
        client.cookies.clear()
        assert client.get("/api/v1/tasks", headers={"Authorization": f"Bearer {created['token']}"}).status_code == 401
        assert client.get("/api/v1/tasks", headers={"Authorization": "Bearer dcp_nope"}).status_code == 401

    def test_secret_shown_once_and_stored_hashed(self, client, test_db):
        login(client, *ADMIN)
        created = _make_token(client)
        listing = client.get("/api/v1/integrations/api-tokens").json()
        assert "token" not in listing[0] and listing[0]["prefix"] == created["token"][:8]


class TestWebhooks:
    @pytest.mark.parametrize("url", [
        "http://127.0.0.1/hook", "https://localhost/x", "https://169.254.169.254/latest",
        "https://10.0.0.5/x", "ftp://example.com/x", "https://user:pw@example.com/x",
    ])
    def test_ssrf_targets_rejected(self, url):
        from app.core.errors import ValidationFailedError
        with pytest.raises(ValidationFailedError):
            webhook_service.validate_target_url(url)

    def test_create_requires_admin_permission(self, client, test_db):
        make_user(test_db, email="wh@interdec.com", role_names=["Accountable PM"])
        login(client, "wh@interdec.com", "Secret!1234")
        r = client.post("/api/v1/integrations/webhooks", json={"url": "https://example.com/h"})
        assert r.status_code == 404

    def test_signature_is_verifiable(self):
        sig = webhook_service.sign("s3cret", "100", b"{}")
        import hashlib, hmac
        assert sig == "sha256=" + hmac.new(b"s3cret", b"100.{}", hashlib.sha256).hexdigest()


class TestRecurring:
    def _tpl(self, db, pm, owner, **kw):
        row = RecurringTask(
            created_by_id=owner.id, title="Weekly stock count", priority="low", accountable_pm_id=pm.id,
            visibility_mode="participants", department_ids=[], frequency="weekly", interval=1,
            due_after_days=5, next_run_on=date.today(), active=True, **kw)
        db.add(row)
        db.commit()
        return row

    def test_due_template_creates_task_and_advances(self, client, test_db):
        admin = test_db.query(User).filter_by(email="admin@interdec.com").first()
        tpl = self._tpl(test_db, admin, admin)
        out = recurrence_service.run_due(test_db)
        assert out["created"] == 1
        task = test_db.query(Task).filter_by(title="Weekly stock count").one()
        assert task.due_date == date.today() + timedelta(days=5)
        test_db.refresh(tpl)
        assert tpl.next_run_on == date.today() + timedelta(days=7)
        assert recurrence_service.run_due(test_db)["created"] == 0  # idempotent same day

    def test_missed_periods_are_not_backfilled(self, client, test_db):
        admin = test_db.query(User).filter_by(email="admin@interdec.com").first()
        tpl = self._tpl(test_db, admin, admin)
        tpl.next_run_on = date.today() - timedelta(days=30)
        test_db.commit()
        assert recurrence_service.run_due(test_db)["created"] == 1
        test_db.refresh(tpl)
        assert tpl.next_run_on > date.today()

    def test_monthly_advance_clamps_day(self):
        assert recurrence_service.advance(date(2026, 1, 31), "monthly", 1) == date(2026, 2, 28)

    def test_owner_without_permission_records_error(self, client, test_db):
        pm = make_user(test_db, email="rpm@interdec.com", role_names=["Department Member"])
        tpl = self._tpl(test_db, pm, pm)
        out = recurrence_service.run_due(test_db)
        assert out["failed"] == 1
        test_db.refresh(tpl)
        assert "can no longer create tasks" in tpl.last_error

    def test_api_create_and_isolation(self, client, test_db):
        pm = make_user(test_db, email="rpm2@interdec.com", role_names=["Accountable PM"])
        login(client, *ADMIN)
        r = client.post("/api/v1/integrations/recurring", json={
            "title": "Monthly review", "accountable_pm_id": str(pm.id), "frequency": "monthly"})
        assert r.status_code == 201, r.text
        rid = r.json()["id"]
        client.post("/api/v1/auth/logout")
        login(client, "rpm2@interdec.com", "Secret!1234")
        assert client.get("/api/v1/integrations/recurring").json() == []
        assert client.delete(f"/api/v1/integrations/recurring/{rid}").status_code == 404


def test_timezone_preference_validated(client, test_db):
    login(client, *ADMIN)
    ok = client.put("/api/v1/me/preferences", json={"timezone": "Africa/Lagos"})
    assert ok.status_code == 200 and ok.json()["timezone"] == "Africa/Lagos"
    assert client.put("/api/v1/me/preferences", json={"timezone": "Mars/Base"}).status_code == 422
