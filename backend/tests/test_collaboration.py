"""Phase 6 - Collaboration tests (spec MOD-005/MOD-006, Phase 6 exit criteria
"Restricted content remains protected across collaboration features").

Mandatory security scenarios covered (spec security.mandatory_test_scenarios):
- User A cannot retrieve another task's comments.
- User A cannot download another task's attachments.
"""

import hashlib
import uuid

from fastapi.testclient import TestClient

from app.models import AccessLevel, Task, User
from app.models.collaboration import Comment
from tests.conftest import login, make_user


def _create_task(client: TestClient, *, pm_id: str, **overrides) -> dict:
    payload = {
        "title": "Quarterly audit prep",
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
# Comments
# ---------------------------------------------------------------------------

class TestComments:
    def test_author_can_comment_and_list_is_ordered(self, client, test_db):
        admin = test_db.query(User).filter_by(email="admin@interdec.com").first()
        pm = make_user(test_db, email="cpm1@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))

        first = client.post(f"/api/v1/tasks/{task['id']}/comments", json={"body": "Kickoff notes."})
        second = client.post(f"/api/v1/tasks/{task['id']}/comments", json={"body": "Second comment."})
        assert first.status_code == 201 and second.status_code == 201
        assert first.json()["author"]["id"] == str(admin.id)

        listing = client.get(f"/api/v1/tasks/{task['id']}/comments").json()
        assert [c["body"] for c in listing] == ["Kickoff notes.", "Second comment."]

    def test_view_level_grantee_may_comment(self, client, test_db):
        pm = make_user(test_db, email="cpm2@interdec.com", role_names=["Accountable PM"])
        viewer = make_user(test_db, email="viewer1@interdec.com", role_names=["Department Member"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        response = client.post(f"/api/v1/tasks/{task['id']}/access-grants", json={
            "user_id": str(viewer.id), "access_level": "view",
        })
        assert response.status_code == 201

        login(client, "viewer1@interdec.com", "Secret!1234")
        created = client.post(f"/api/v1/tasks/{task['id']}/comments", json={"body": "Viewer can contribute."})
        assert created.status_code == 201
        assert client.get(f"/api/v1/tasks/{task['id']}/comments").json()[0]["body"] == "Viewer can contribute."

    def test_outsider_gets_404_not_403_on_comments(self, client, test_db):
        pm = make_user(test_db, email="cpm3@interdec.com", role_names=["Accountable PM"])
        outsider = make_user(test_db, email="outc@interdec.com", role_names=["Department Member"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id), visibility_mode="private")
        client.post(f"/api/v1/tasks/{task['id']}/comments", json={"body": "secret note"})

        login(client, "outc@interdec.com", "Secret!1234")
        assert client.get(f"/api/v1/tasks/{task['id']}/comments").status_code == 404
        created = client.post(f"/api/v1/tasks/{task['id']}/comments", json={"body": "intrusion"})
        assert created.status_code == 404

    def test_cross_task_comment_access_denied(self, client, test_db):
        """Mandatory scenario: User A cannot retrieve another task's comments."""
        pm = make_user(test_db, email="cpm4@interdec.com", role_names=["Accountable PM"])
        user_a = make_user(test_db, email="usera@interdec.com", role_names=["Department Member"])
        login(client, "admin@interdec.com", "DecOps!2026")
        restricted = _create_task(client, pm_id=str(pm.id), visibility_mode="custom",
                                  grant_user_ids=[str(user_a.id)], grant_access_level="view")
        other_task = _create_task(client, pm_id=str(pm.id), visibility_mode="private")
        client.post(f"/api/v1/tasks/{other_task['id']}/comments", json={"body": "top secret discussion"})

        # User A is authorized on `restricted` only.
        login(client, "usera@interdec.com", "Secret!1234")
        # Try to smuggle the other task's comments through every reachable route.
        assert client.get(f"/api/v1/tasks/{other_task['id']}/comments").status_code == 404
        smuggle = client.post(
            f"/api/v1/tasks/{restricted['id']}/comments",
            json={"body": "x", "work_item_id": str(uuid.uuid4())},
        )
        assert smuggle.status_code == 422  # unknown work item on this task
        # The restricted task's own comment list is empty and does not leak.
        assert client.get(f"/api/v1/tasks/{restricted['id']}/comments").json() == []

    def test_empty_comment_rejected(self, client, test_db):
        pm = make_user(test_db, email="cpm5@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        response = client.post(f"/api/v1/tasks/{task['id']}/comments", json={"body": "   "})
        assert response.status_code == 422

    def test_author_can_soft_delete_own_comment(self, client, test_db):
        pm = make_user(test_db, email="cpm6@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        comment = client.post(f"/api/v1/tasks/{task['id']}/comments", json={"body": "to be removed"}).json()

        deleted = client.delete(f"/api/v1/tasks/{task['id']}/comments/{comment['id']}")
        assert deleted.status_code == 204
        assert client.get(f"/api/v1/tasks/{task['id']}/comments").json() == []
        # Row persists (soft delete, audit intact).
        row = test_db.query(Comment).filter_by(id=uuid.UUID(comment["id"])).first()
        assert row is not None and row.deleted_at is not None

    def test_non_author_cannot_delete_someone_elses_comment_without_manage(self, client, test_db):
        pm = make_user(test_db, email="cpm7@interdec.com", role_names=["Accountable PM"])
        author = make_user(test_db, email="author1@interdec.com", role_names=["Supporting PM"])
        member = make_user(test_db, email="member1@interdec.com", role_names=["Department Member"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        client.post(f"/api/v1/tasks/{task['id']}/access-grants", json={
            "user_id": str(author.id), "access_level": "operate"})
        client.post(f"/api/v1/tasks/{task['id']}/access-grants", json={
            "user_id": str(member.id), "access_level": "view"})

        login(client, "author1@interdec.com", "Secret!1234")
        comment = client.post(f"/api/v1/tasks/{task['id']}/comments", json={"body": "authored"}).json()

        login(client, "member1@interdec.com", "Secret!1234")
        # A view-grantee cannot even confirm another user's comment id...
        response = client.delete(f"/api/v1/tasks/{task['id']}/comments/{comment['id']}")
        assert response.status_code in (403, 404)
        # ...and the comment survives either way.
        login(client, "author1@interdec.com", "Secret!1234")
        assert client.get(f"/api/v1/tasks/{task['id']}/comments").json()[0]["body"] == "authored"


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------

class TestAttachments:
    def test_upload_download_roundtrip_with_checksum(self, client, test_db):
        pm = make_user(test_db, email="apm1@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))

        content = b"interdec quarterly figures, confidential"
        uploaded = client.post(
            f"/api/v1/tasks/{task['id']}/attachments",
            files={"file": ("figures.csv", content, "text/csv")},
        )
        assert uploaded.status_code == 201, uploaded.text
        data = uploaded.json()
        assert data["original_filename"] == "figures.csv"
        assert data["checksum"] == hashlib.sha256(content).hexdigest()
        assert data["size_bytes"] == len(content)
        # The storage key must never be exposed.
        assert "storage_key" not in data

        download = client.get(f"/api/v1/tasks/{task['id']}/attachments/{data['id']}/download")
        assert download.status_code == 200
        assert download.content == content
        assert "figures.csv" in download.headers.get("content-disposition", "")

    def test_list_attachments_and_activity(self, client, test_db):
        pm = make_user(test_db, email="apm2@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        client.post(f"/api/v1/tasks/{task['id']}/attachments",
                    files={"file": ("a.txt", b"A", "text/plain")})
        client.post(f"/api/v1/tasks/{task['id']}/attachments",
                    files={"file": ("b.txt", b"B", "text/plain")})

        listing = client.get(f"/api/v1/tasks/{task['id']}/attachments").json()
        assert {a["original_filename"] for a in listing} == {"a.txt", "b.txt"}
        activity = client.get(f"/api/v1/tasks/{task['id']}/activity").json()
        assert any(a["activity_type"] == "attachment.added" for a in activity)

    def test_disallowed_extension_rejected(self, client, test_db):
        pm = make_user(test_db, email="apm3@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        response = client.post(
            f"/api/v1/tasks/{task['id']}/attachments",
            files={"file": ("evil.exe", b"MZ...", "application/octet-stream")},
        )
        assert response.status_code == 422
        assert "not allowed" in response.json()["error"]["message"]

    def test_empty_file_rejected(self, client, test_db):
        pm = make_user(test_db, email="apm4@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        response = client.post(
            f"/api/v1/tasks/{task['id']}/attachments",
            files={"file": ("empty.txt", b"", "text/plain")},
        )
        assert response.status_code == 422

    def test_outsider_cannot_download(self, client, test_db):
        pm = make_user(test_db, email="apm5@interdec.com", role_names=["Accountable PM"])
        outsider = make_user(test_db, email="outa@interdec.com", role_names=["Department Member"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id), visibility_mode="private")
        attachment = client.post(
            f"/api/v1/tasks/{task['id']}/attachments",
            files={"file": ("private.pdf", b"%PDF-1.7 secret", "application/pdf")},
        ).json()

        login(client, "outa@interdec.com", "Secret!1234")
        assert client.get(f"/api/v1/tasks/{task['id']}/attachments").status_code == 404
        download = client.get(f"/api/v1/tasks/{task['id']}/attachments/{attachment['id']}/download")
        assert download.status_code == 404

    def test_cross_task_attachment_download_denied(self, client, test_db):
        """Mandatory scenario: User A cannot download another task's attachments."""
        pm = make_user(test_db, email="apm6@interdec.com", role_names=["Accountable PM"])
        user_a = make_user(test_db, email="userax@interdec.com", role_names=["Department Member"])
        login(client, "admin@interdec.com", "DecOps!2026")
        restricted = _create_task(client, pm_id=str(pm.id), visibility_mode="custom",
                                  grant_user_ids=[str(user_a.id)], grant_access_level="operate")
        other_task = _create_task(client, pm_id=str(pm.id), visibility_mode="private")
        secret = client.post(
            f"/api/v1/tasks/{other_task['id']}/attachments",
            files={"file": ("secret.txt", b"restricted bytes", "text/plain")},
        ).json()

        login(client, "userax@interdec.com", "Secret!1234")
        download = client.get(f"/api/v1/tasks/{restricted['id']}/attachments/{secret['id']}/download")
        assert download.status_code == 404
        # Enumerating the other task's list is impossible too.
        assert client.get(f"/api/v1/tasks/{other_task['id']}/attachments").status_code == 404

    def test_uploader_can_delete_own_attachment(self, client, test_db):
        pm = make_user(test_db, email="apm7@interdec.com", role_names=["Accountable PM"])
        member = make_user(test_db, email="memup@interdec.com", role_names=["Department Member"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        client.post(f"/api/v1/tasks/{task['id']}/access-grants", json={
            "user_id": str(member.id), "access_level": "operate"})

        login(client, "memup@interdec.com", "Secret!1234")
        attachment = client.post(
            f"/api/v1/tasks/{task['id']}/attachments",
            files={"file": ("mine.txt", b"mine", "text/plain")},
        ).json()
        deleted = client.delete(f"/api/v1/tasks/{task['id']}/attachments/{attachment['id']}")
        assert deleted.status_code == 204
        assert client.get(f"/api/v1/tasks/{task['id']}/attachments").json() == []
