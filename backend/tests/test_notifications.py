"""Phase 6 — Notifications & transactional outbox tests (spec exit criteria:
"Notification processing is retry-safe"; mandatory scenario: "A background
notification job does not disclose information after access revocation")."""

import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.domain import notifications as ntf
from app.models import Task, User
from app.models.collaboration import Notification, NotificationPreference, OutboxEvent, OutboxStatus
from app.services import notification_service
from tests.conftest import login, make_user
from tests.test_collaboration import _create_task


def _process(db):
    return notification_service.process_due_events(db)


def _events(db):
    return db.query(OutboxEvent).all()


def _notifications_for(db, user: User) -> list[Notification]:
    return db.query(Notification).filter_by(recipient_id=user.id).all()


# ---------------------------------------------------------------------------
# Domain rules (pure)
# ---------------------------------------------------------------------------

class TestDomainRules:
    def test_actor_excluded_from_default_circle(self):
        actor = uuid.uuid4()
        circle = ntf.default_circle(
            actor_id=actor, accountable_pm_id=uuid.uuid4(),
            creator_id=uuid.uuid4(), participant_ids={actor, uuid.uuid4()},
        )
        assert actor not in circle and len(circle) == 3

    def test_confidential_email_subject_hides_title(self):
        subject = ntf.email_subject(
            event_label="Task completed", task_number="TSK-2026-0007",
            task_title="Layoff plan Q4", visibility_mode="private",
        )
        assert "Layoff" not in subject
        assert "TSK-2026-0007" in subject

    def test_public_email_subject_contains_title(self):
        subject = ntf.email_subject(
            event_label="Task completed", task_number="TSK-2026-0007",
            task_title="Office move", visibility_mode="participants",
        )
        assert "Office move" in subject and "TSK-2026-0007" in subject

    def test_backoff_is_exponential_and_capped(self):
        base = 30.0
        assert ntf.backoff_delay(1, base_seconds=base) == 30
        assert ntf.backoff_delay(2, base_seconds=base) == 60
        assert ntf.backoff_delay(3, base_seconds=base) == 120
        assert ntf.backoff_delay(20, base_seconds=base) == 3600  # cap


# ---------------------------------------------------------------------------
# Producer: transactional outbox
# ---------------------------------------------------------------------------

class TestTransactionalOutbox:
    def test_assignment_enqueues_event_and_rolls_back_cleanly(self, client, test_db):
        pm = make_user(test_db, email="npm1@interdec.com", role_names=["Accountable PM"])
        support = make_user(test_db, email="nsup1@interdec.com", role_names=["Supporting PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        client.post(f"/api/v1/tasks/{task['id']}/assignments", json={
            "user_id": str(support.id), "assignment_role": "supporting_pm"})

        # The assignment mutation enqueued a same-transaction outbox row.
        assert any(e.event_type == ntf.EventType.SUPPORTING_PM_ADDED for e in _events(test_db))

        # A rolled-back transaction must leave NO outbox row behind:
        # "Do not send notifications for transactions that ultimately roll back."
        orphan = notification_service.record_event(
            test_db, event_type=ntf.EventType.TASK_COMPLETED, task_id=task["id"], actor=None,
        )
        assert orphan is not None
        test_db.rollback()
        remaining_types = {e.event_type for e in _events(test_db)}
        assert ntf.EventType.TASK_COMPLETED not in remaining_types

    def test_worker_delivers_targeted_assignment_excluding_actor(self, client, test_db):
        admin = test_db.query(User).filter_by(email="admin@interdec.com").first()
        pm = make_user(test_db, email="npm2@interdec.com", role_names=["Accountable PM"])
        support = make_user(test_db, email="nsup2@interdec.com", role_names=["Supporting PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        client.post(f"/api/v1/tasks/{task['id']}/assignments", json={
            "user_id": str(support.id), "assignment_role": "supporting_pm"})
        test_db.commit()

        result = _process(test_db)
        assert result["claimed"] >= 1 and result["processed"] >= 1

        # The target user was notified; the acting admin was not.
        support_notes = _notifications_for(test_db, support)
        assert [n.event_type for n in support_notes] == [ntf.EventType.SUPPORTING_PM_ADDED]
        assert _notifications_for(test_db, admin) == []
        assert support_notes[0].payload["task_number"].startswith("TSK-")

    def test_processing_is_idempotent(self, client, test_db):
        pm = make_user(test_db, email="npm3@interdec.com", role_names=["Accountable PM"])
        support = make_user(test_db, email="nsup3@interdec.com", role_names=["Supporting PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        client.post(f"/api/v1/tasks/{task['id']}/assignments", json={
            "user_id": str(support.id), "assignment_role": "supporting_pm"})
        test_db.commit()

        first = _process(test_db)
        second = _process(test_db)
        assert first["processed"] >= 1
        assert second["claimed"] == 0  # already processed; nothing re-claimed
        assert len(_notifications_for(test_db, support)) == 1

    def test_replay_of_claimed_event_does_not_duplicate(self, client, test_db):
        pm = make_user(test_db, email="npm4@interdec.com", role_names=["Accountable PM"])
        support = make_user(test_db, email="nsup4@interdec.com", role_names=["Supporting PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        client.post(f"/api/v1/tasks/{task['id']}/assignments", json={
            "user_id": str(support.id), "assignment_role": "supporting_pm"})
        test_db.commit()

        event = next(e for e in _events(test_db) if e.event_type == ntf.EventType.SUPPORTING_PM_ADDED)
        notification_service.process_event(test_db, event)
        test_db.commit()
        # Simulate a crashed worker re-claiming the same event.
        event.status = OutboxStatus.processing
        notification_service.process_event(test_db, event)
        test_db.commit()
        assert len(_notifications_for(test_db, support)) == 1

    def test_transition_events_fan_out_to_circle(self, client, test_db):
        admin = test_db.query(User).filter_by(email="admin@interdec.com").first()
        pm = make_user(test_db, email="npm5@interdec.com", role_names=["Accountable PM"])
        support = make_user(test_db, email="support1@interdec.com", role_names=["Supporting PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        client.post(f"/api/v1/tasks/{task['id']}/assignments", json={
            "user_id": str(support.id), "assignment_role": "supporting_pm"})
        # open -> in_progress -> blocked
        client.post(f"/api/v1/tasks/{task['id']}/transition", json={"to_status": "open"})
        client.post(f"/api/v1/tasks/{task['id']}/transition", json={"to_status": "in_progress"})
        client.post(f"/api/v1/tasks/{task['id']}/transition",
                    json={"to_status": "blocked", "reason": "waiting on vendor"})
        test_db.commit()
        _process(test_db)

        pm_types = {n.event_type for n in _notifications_for(test_db, pm)}
        assert pm_types == {ntf.EventType.TASK_BLOCKED}
        # The supporting PM received both the targeted assignment notification
        # and the circle fan-out of the blocked transition.
        support_types = {n.event_type for n in _notifications_for(test_db, support)}
        assert support_types == {ntf.EventType.SUPPORTING_PM_ADDED, ntf.EventType.TASK_BLOCKED}
        # The acting admin received nothing of their own actions.
        assert _notifications_for(test_db, admin) == []


# ---------------------------------------------------------------------------
# Security: revocation-safe delivery
# ---------------------------------------------------------------------------

class TestRevocationSafety:
    def test_background_job_does_not_disclose_after_revocation(self, client, test_db):
        """Mandatory scenario. Events are enqueued while the users still have
        access; one participant's access is revoked before the worker ever
        runs — the job must not disclose anything to them."""
        admin = test_db.query(User).filter_by(email="admin@interdec.com").first()
        pm = make_user(test_db, email="rspm@interdec.com", role_names=["Accountable PM"])
        revoked_user = make_user(test_db, email="revoked1@interdec.com", role_names=["Supporting PM"])
        kept_user = make_user(test_db, email="kept1@interdec.com", role_names=["Supporting PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id), visibility_mode="participants")
        for user in (revoked_user, kept_user):
            response = client.post(f"/api/v1/tasks/{task['id']}/assignments", json={
                "user_id": str(user.id), "assignment_role": "supporting_pm"})
            assert response.status_code == 201
        client.post(f"/api/v1/tasks/{task['id']}/transition", json={"to_status": "open"})
        client.post(f"/api/v1/tasks/{task['id']}/transition", json={"to_status": "in_progress"})
        client.post(f"/api/v1/tasks/{task['id']}/transition",
                    json={"to_status": "blocked", "reason": "waiting on vendor"})

        # Revoke ONE participant's assignment BEFORE the worker runs.
        assignments = client.get(f"/api/v1/tasks/{task['id']}").json()["assignments"]
        to_revoke = next(a["id"] for a in assignments
                         if a["user_id"] == str(revoked_user.id) and a["revoked_at"] is None)
        assert client.delete(f"/api/v1/tasks/{task['id']}/assignments/{to_revoke}").status_code == 204
        test_db.commit()

        _process(test_db)

        # Revoked user: nothing (their targeted event AND circle events suppressed).
        assert _notifications_for(test_db, revoked_user) == []
        # Kept participants received their events; the actor received none.
        kept_types = {n.event_type for n in _notifications_for(test_db, kept_user)}
        assert kept_types == {ntf.EventType.SUPPORTING_PM_ADDED, ntf.EventType.TASK_BLOCKED}
        pm_types = {n.event_type for n in _notifications_for(test_db, pm)}
        assert ntf.EventType.TASK_BLOCKED in pm_types
        assert _notifications_for(test_db, admin) == []

    def test_targeted_access_grant_notifies_only_target(self, client, test_db):
        pm = make_user(test_db, email="rspm2@interdec.com", role_names=["Accountable PM"])
        target = make_user(test_db, email="target1@interdec.com", role_names=["Department Member"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id), visibility_mode="private")
        client.post(f"/api/v1/tasks/{task['id']}/access-grants", json={
            "user_id": str(target.id), "access_level": "view"})
        test_db.commit()
        _process(test_db)

        # Target user learned about the grant; nobody else did.
        types = {n.event_type for n in _notifications_for(test_db, target)}
        assert ntf.EventType.ACCESS_GRANTED in types
        assert _notifications_for(test_db, pm) == []


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------

class TestPreferences:
    def test_disabled_in_app_preference_suppresses_delivery(self, client, test_db):
        pm = make_user(test_db, email="pref1@interdec.com", role_names=["Accountable PM"])
        support = make_user(test_db, email="prefs1@interdec.com", role_names=["Supporting PM"])
        test_db.add(NotificationPreference(
            user_id=support.id, event_type=ntf.EventType.SUPPORTING_PM_ADDED,
            in_app_enabled=False, email_enabled=False,
        ))
        test_db.commit()

        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        client.post(f"/api/v1/tasks/{task['id']}/assignments", json={
            "user_id": str(support.id), "assignment_role": "supporting_pm"})
        test_db.commit()
        _process(test_db)

        assert _notifications_for(test_db, support) == []

    def test_default_is_enabled_without_preference_rows(self, client, test_db):
        pm = make_user(test_db, email="pref2@interdec.com", role_names=["Accountable PM"])
        assert notification_service.wants(test_db, pm.id, ntf.EventType.TASK_ASSIGNED, "in_app")

    def test_preference_api_roundtrip(self, client, test_db):
        make_user(test_db, email="prefapi@interdec.com", role_names=["Department Member"])
        login(client, "prefapi@interdec.com", "Secret!1234")
        updated = client.put("/api/v1/notifications/preferences", json={
            "event_type": "task_assigned", "in_app_enabled": False, "email_enabled": True})
        assert updated.status_code == 200
        listing = client.get("/api/v1/notifications/preferences").json()
        pref = next(p for p in listing["preferences"] if p["event_type"] == "task_assigned")
        assert pref["in_app_enabled"] is False and pref["email_enabled"] is True

        bad = client.put("/api/v1/notifications/preferences", json={
            "event_type": "not_an_event", "in_app_enabled": True, "email_enabled": True})
        assert bad.status_code == 422


# ---------------------------------------------------------------------------
# Retry handling
# ---------------------------------------------------------------------------

class TestRetrySafety:
    def test_transient_failure_is_retried_with_backoff(self, client, test_db, monkeypatch):
        pm = make_user(test_db, email="retry1@interdec.com", role_names=["Accountable PM"])
        support = make_user(test_db, email="retrys@interdec.com", role_names=["Supporting PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        client.post(f"/api/v1/tasks/{task['id']}/assignments", json={
            "user_id": str(support.id), "assignment_role": "supporting_pm"})
        test_db.commit()

        # Make delivery blow up once by breaking the authorization check transiently.
        original = notification_service._can_see_task
        calls = {"n": 0}

        def flaky(db, user_id, task_obj):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("transient datastore hiccup")
            return original(db, user_id, task_obj)

        monkeypatch.setattr(notification_service, "_can_see_task", flaky)
        first = _process(test_db)
        assert first["retry"] == 1
        event = next(e for e in _events(test_db) if e.status == OutboxStatus.pending)
        assert event.attempt_count == 1
        assert event.next_attempt_at > datetime.now(UTC)
        monkeypatch.undo()

        # Force the event due and process again: succeeds, no duplicates.
        event.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        test_db.commit()
        second = _process(test_db)
        assert second["processed"] == 1
        assert len(_notifications_for(test_db, support)) == 1

    def test_permanent_failure_is_recorded_not_retried(self, client, test_db):
        event = OutboxEvent(
            event_type=ntf.EventType.TASK_COMPLETED,
            aggregate_type="task",
            aggregate_id=str(uuid.uuid4()),  # task does not exist
            payload={"actor_id": None},
            status=OutboxStatus.pending,
            next_attempt_at=datetime.now(UTC),
        )
        test_db.add(event)
        test_db.commit()
        result = _process(test_db)
        assert result["permanent"] == 1
        assert event.status == OutboxStatus.permanent_failure
        assert "no longer exists" in (event.last_error or "")

    def test_max_attempts_ends_in_permanent_failure(self, client, test_db, monkeypatch):
        pm = make_user(test_db, email="maxretry@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        client.post(f"/api/v1/tasks/{task['id']}/transition", json={"to_status": "open"})
        client.post(f"/api/v1/tasks/{task['id']}/transition", json={"to_status": "in_progress"})
        client.post(f"/api/v1/tasks/{task['id']}/transition",
                    json={"to_status": "blocked", "reason": "vendor delay"})
        test_db.commit()

        def boom(db, event, task):
            raise RuntimeError("persistent outage")

        monkeypatch.setattr(notification_service, "_recipients_for", boom)
        backup = settings.outbox_max_attempts
        settings.outbox_max_attempts = 2
        try:
            blocked_event = next(e for e in _events(test_db)
                                 if e.event_type == ntf.EventType.TASK_BLOCKED)
            notification_service.process_event(test_db, blocked_event)
            assert blocked_event.status == OutboxStatus.pending
            assert blocked_event.attempt_count == 1
            notification_service.process_event(test_db, blocked_event)
            assert blocked_event.status == OutboxStatus.permanent_failure
            assert "persistent outage" in (blocked_event.last_error or "")
        finally:
            settings.outbox_max_attempts = backup
            monkeypatch.undo()


# ---------------------------------------------------------------------------
# Deadline sweep
# ---------------------------------------------------------------------------

class TestDeadlineSweep:
    def _task_row(self, db, pm: User, **overrides) -> Task:
        task = Task(
            task_number=f"TSK-2026-{uuid.uuid4().hex[:4].upper()}",
            title="Sweep target", priority="high", status="in_progress",
            accountable_pm_id=pm.id, created_by_id=pm.id,
            visibility_mode="participants", **overrides,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return task

    def test_overdue_task_notifies_pm_once_per_window(self, test_db):
        pm = make_user(test_db, email="sweep1@interdec.com", role_names=["Accountable PM"])
        self._task_row(test_db, pm, due_date=datetime.now(UTC).date() - timedelta(days=2))

        first = notification_service.sweep_deadlines(test_db)
        assert first["created"] == 1
        notification = _notifications_for(test_db, pm)[0]
        assert notification.event_type == ntf.EventType.TASK_OVERDUE

        # Second sweep inside the dedup window creates nothing new.
        second = notification_service.sweep_deadlines(test_db)
        assert second["created"] == 0
        assert len(_notifications_for(test_db, pm)) == 1

    def test_upcoming_deadline_notifies(self, test_db):
        pm = make_user(test_db, email="sweep2@interdec.com", role_names=["Accountable PM"])
        self._task_row(test_db, pm, due_date=datetime.now(UTC).date() + timedelta(days=2))
        result = notification_service.sweep_deadlines(test_db)
        assert result["created"] == 1
        assert _notifications_for(test_db, pm)[0].event_type == ntf.EventType.DEADLINE_APPROACHING

    def test_far_future_deadline_ignored_and_completed_tasks_skipped(self, test_db):
        pm = make_user(test_db, email="sweep3@interdec.com", role_names=["Accountable PM"])
        self._task_row(test_db, pm, due_date=datetime.now(UTC).date() + timedelta(days=30))
        task = self._task_row(test_db, pm, due_date=datetime.now(UTC).date() - timedelta(days=1))
        task.status = "completed"
        test_db.commit()
        result = notification_service.sweep_deadlines(test_db)
        assert result["created"] == 0


# ---------------------------------------------------------------------------
# Email channel (optional; disabled by default)
# ---------------------------------------------------------------------------

class TestEmailChannel:
    def test_email_disabled_by_default_no_send(self, client, test_db, monkeypatch):
        sent = []
        monkeypatch.setattr("app.services.email_sender.smtplib.SMTP", lambda *a, **k: sent.append(1))
        pm = make_user(test_db, email="email1@interdec.com", role_names=["Accountable PM"])
        support = make_user(test_db, email="emails1@interdec.com", role_names=["Supporting PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        client.post(f"/api/v1/tasks/{task['id']}/assignments", json={
            "user_id": str(support.id), "assignment_role": "supporting_pm"})
        test_db.commit()
        _process(test_db)
        assert sent == []  # no SMTP activity when the channel is disabled
        assert len(_notifications_for(test_db, support)) == 1  # in-app still worked

    def test_email_subject_redacted_for_confidential_tasks(self, client, test_db, monkeypatch):
        captured = []

        def fake_send(*, to_email, subject, body):
            captured.append((to_email, subject, body))

        monkeypatch.setattr(notification_service.email_sender, "send_email", fake_send)
        monkeypatch.setattr(notification_service.settings, "email_notifications_enabled", True)

        pm = make_user(test_db, email="email2@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id), visibility_mode="private",
                            title="Secret restructuring plan")
        # A circle event fans out to the PM (actor excluded); private task.
        client.post(f"/api/v1/tasks/{task['id']}/transition", json={"to_status": "open"})
        client.post(f"/api/v1/tasks/{task['id']}/transition", json={"to_status": "in_progress"})
        client.post(f"/api/v1/tasks/{task['id']}/transition",
                    json={"to_status": "blocked", "reason": "waiting"})
        test_db.commit()
        _process(test_db)

        assert captured, "email should have been attempted"
        for _, subject, _ in captured:
            assert "Secret restructuring" not in subject
            assert task["task_number"] in subject


# ---------------------------------------------------------------------------
# Notification center API
# ---------------------------------------------------------------------------

class TestNotificationCenter:
    def test_read_flow_and_unread_count(self, client, test_db):
        pm = make_user(test_db, email="center1@interdec.com", role_names=["Accountable PM"])
        support = make_user(test_db, email="centers1@interdec.com", role_names=["Supporting PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        client.post(f"/api/v1/tasks/{task['id']}/assignments", json={
            "user_id": str(support.id), "assignment_role": "supporting_pm"})
        client.post(f"/api/v1/tasks/{task['id']}/transition", json={"to_status": "open"})
        client.post(f"/api/v1/tasks/{task['id']}/transition", json={"to_status": "in_progress"})
        client.post(f"/api/v1/tasks/{task['id']}/transition",
                    json={"to_status": "blocked", "reason": "vendor delay"})
        test_db.commit()
        _process(test_db)

        login(client, "center1@interdec.com", "Secret!1234")
        badge = client.get("/api/v1/notifications/unread-count").json()
        assert badge["unread"] >= 1
        listing = client.get("/api/v1/notifications").json()
        assert listing["unread"] >= 1 and len(listing["items"]) == listing["unread"]

        notification_id = listing["items"][0]["id"]
        marked = client.post(f"/api/v1/notifications/{notification_id}/read")
        assert marked.status_code == 200
        assert marked.json()["read_at"] is not None
        assert client.get("/api/v1/notifications/unread-count").json()["unread"] == listing["unread"] - 1

    def test_cannot_read_someone_elses_notification(self, client, test_db):
        pm = make_user(test_db, email="center2@interdec.com", role_names=["Accountable PM"])
        support = make_user(test_db, email="centers2@interdec.com", role_names=["Supporting PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        client.post(f"/api/v1/tasks/{task['id']}/assignments", json={
            "user_id": str(support.id), "assignment_role": "supporting_pm"})
        test_db.commit()
        _process(test_db)

        notification = _notifications_for(test_db, support)[0]
        make_user(test_db, email="stranger1@interdec.com", role_names=["Department Member"])
        login(client, "stranger1@interdec.com", "Secret!1234")
        response = client.post(f"/api/v1/notifications/{notification.id}/read")
        assert response.status_code == 404

    def test_read_all(self, client, test_db):
        pm = make_user(test_db, email="center3@interdec.com", role_names=["Accountable PM"])
        login(client, "admin@interdec.com", "DecOps!2026")
        task = _create_task(client, pm_id=str(pm.id))
        client.post(f"/api/v1/tasks/{task['id']}/transition", json={"to_status": "open"})
        client.post(f"/api/v1/tasks/{task['id']}/transition", json={"to_status": "in_progress"})
        client.post(f"/api/v1/tasks/{task['id']}/transition",
                    json={"to_status": "blocked", "reason": "vendor"})
        test_db.commit()
        _process(test_db)

        login(client, "center3@interdec.com", "Secret!1234")
        before = client.get("/api/v1/notifications/unread-count").json()["unread"]
        assert before >= 1
        cleared = client.post("/api/v1/notifications/read-all")
        assert cleared.status_code == 200
        assert client.get("/api/v1/notifications/unread-count").json()["unread"] == 0

    def test_process_endpoint_admin_gated(self, client, test_db):
        make_user(test_db, email="procuser@interdec.com", role_names=["Department Member"])
        login(client, "procuser@interdec.com", "Secret!1234")
        assert client.post("/api/v1/notifications/process").status_code == 404

        login(client, "admin@interdec.com", "DecOps!2026")
        response = client.post("/api/v1/notifications/process")
        assert response.status_code == 200
        assert "claimed" in response.json()
