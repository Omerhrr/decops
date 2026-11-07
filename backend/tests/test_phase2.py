"""Phase 2: mentions, saved filters, bulk actions, search, email rendering."""

from app.models import User
from app.models.collaboration import Notification
from app.services import notification_service
from tests.conftest import login, make_user

ADMIN = ("admin@interdec.com", "DecOps!2026")


def _task(client, pm_id, **kw):
    payload = {"title": "Phase two task", "priority": "high", "accountable_pm_id": pm_id,
               "due_date": "2026-12-31", "visibility_mode": "participants"}
    payload.update(kw)
    r = client.post("/api/v1/tasks", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _mention(user):
    return f"@[{user.full_name}](user:{user.id})"


class TestMentions:
    def test_mention_notifies_user_who_can_view(self, client, test_db):
        pm = make_user(test_db, email="mpm@interdec.com", role_names=["Accountable PM"])
        login(client, *ADMIN)
        task = _task(client, str(pm.id))
        r = client.post(f"/api/v1/tasks/{task['id']}/comments", json={"body": f"hi {_mention(pm)} look"})
        assert r.status_code == 201
        notification_service.process_due_events(test_db)
        notes = test_db.query(Notification).filter_by(recipient_id=pm.id, event_type="comment_mention").all()
        assert len(notes) == 1

    def test_mention_of_user_without_access_is_silent(self, client, test_db):
        pm = make_user(test_db, email="mpm2@interdec.com", role_names=["Accountable PM"])
        outsider = make_user(test_db, email="outsider@interdec.com", role_names=["Department Member"])
        login(client, *ADMIN)
        task = _task(client, str(pm.id), visibility_mode="private")
        r = client.post(f"/api/v1/tasks/{task['id']}/comments", json={"body": f"psst {_mention(outsider)}"})
        assert r.status_code == 201
        notification_service.process_due_events(test_db)
        assert test_db.query(Notification).filter_by(recipient_id=outsider.id).count() == 0

    def test_mentionable_lists_only_people_who_can_view(self, client, test_db):
        pm = make_user(test_db, email="mpm3@interdec.com", role_names=["Accountable PM"])
        outsider = make_user(test_db, email="out2@interdec.com", role_names=["Department Member"])
        login(client, *ADMIN)
        task = _task(client, str(pm.id), visibility_mode="private")
        ids = [p["id"] for p in client.get(f"/api/v1/tasks/{task['id']}/mentionable").json()]
        assert str(pm.id) in ids and str(outsider.id) not in ids


class TestSavedFilters:
    def test_crud_and_isolation(self, client, test_db):
        make_user(test_db, email="sf2@interdec.com", role_names=["Accountable PM"])
        login(client, *ADMIN)
        r = client.post("/api/v1/saved-filters", json={"name": "Urgent", "params": {"priority": "high", "bogus": "x"}})
        assert r.status_code == 201 and r.json()["params"] == {"priority": "high"}
        fid = r.json()["id"]
        assert len(client.get("/api/v1/saved-filters").json()) == 1
        client.post("/api/v1/auth/logout")
        login(client, "sf2@interdec.com", "Secret!1234")
        assert client.get("/api/v1/saved-filters").json() == []
        assert client.delete(f"/api/v1/saved-filters/{fid}").status_code == 404


class TestBulk:
    def test_set_priority_and_per_task_results(self, client, test_db):
        pm = make_user(test_db, email="bpm@interdec.com", role_names=["Accountable PM"])
        login(client, *ADMIN)
        a = _task(client, str(pm.id), title="Task A")
        b = _task(client, str(pm.id), title="Task B")
        missing = "00000000-0000-0000-0000-000000000001"
        r = client.post("/api/v1/tasks/bulk", json={
            "task_ids": [a["id"], b["id"], missing], "action": "set_priority", "priority": "low"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["succeeded"] == 2 and body["failed"] == 1
        assert client.get(f"/api/v1/tasks/{a['id']}").json()["priority"] == "low"

    def test_bulk_cannot_touch_tasks_user_cannot_see(self, client, test_db):
        pm = make_user(test_db, email="bpm2@interdec.com", role_names=["Accountable PM"])
        other = make_user(test_db, email="bother@interdec.com", role_names=["Department Member"])
        login(client, *ADMIN)
        t = _task(client, str(pm.id), visibility_mode="private")
        client.post("/api/v1/auth/logout")
        login(client, "bother@interdec.com", "Secret!1234")
        r = client.post("/api/v1/tasks/bulk", json={"task_ids": [t["id"]], "action": "set_priority", "priority": "low"})
        assert r.status_code == 200 and r.json()["failed"] == 1
        client.post("/api/v1/auth/logout")
        login(client, *ADMIN)
        assert client.get(f"/api/v1/tasks/{t['id']}").json()["priority"] == "high"


class TestSearch:
    def test_search_respects_authorization(self, client, test_db):
        pm = make_user(test_db, email="spm@interdec.com", role_names=["Accountable PM"])
        other = make_user(test_db, email="sother@interdec.com", role_names=["Department Member"])
        login(client, *ADMIN)
        _task(client, str(pm.id), title="Zebra secret plan", visibility_mode="private")
        assert len(client.get("/api/v1/search", params={"q": "zebra"}).json()["tasks"]) == 1
        client.post("/api/v1/auth/logout")
        login(client, "sother@interdec.com", "Secret!1234")
        assert client.get("/api/v1/search", params={"q": "zebra"}).json()["tasks"] == []


def test_html_email_escapes_content():
    from app.services.email_sender import render_html
    out = render_html(heading="<b>x</b>", body="a<script>", link="https://x/y?a=1&b=2")
    assert "<script>" not in out and "&lt;script&gt;" in out
