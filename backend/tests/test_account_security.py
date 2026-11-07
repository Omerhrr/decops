"""Password change/reset, forced change, TOTP, sessions, audit viewer, rate limiting."""

import pyotp
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.models import AuditEvent, PasswordResetToken, User
from tests.conftest import login, make_user

PW = "Secret!1234"
NEW = "Brand-new#Pass99"


def _user(db, email="acct@example.com", **kw):
    return make_user(db, email=email, password=PW, **kw)


# ---------------------------------------------------------------- password
def test_change_password_revokes_other_sessions(client, test_db):
    _user(test_db)
    assert login(client, "acct@example.com", PW).status_code == 200
    other = TestClient(client.app)
    other.app.dependency_overrides = client.app.dependency_overrides
    assert login(other, "acct@example.com", PW).status_code == 200

    r = client.post("/api/v1/auth/change-password", json={"current_password": PW, "new_password": NEW})
    assert r.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 200          # current session survives
    assert other.get("/api/v1/auth/me").status_code == 401          # other session revoked
    assert login(TestClient(client.app), "acct@example.com", PW).status_code == 401
    assert login(client, "acct@example.com", NEW).status_code == 200


def test_change_password_rejects_wrong_current_and_weak(client, test_db):
    _user(test_db)
    login(client, "acct@example.com", PW)
    bad = client.post("/api/v1/auth/change-password", json={"current_password": "nope", "new_password": NEW})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "invalid_current_password"
    weak = client.post("/api/v1/auth/change-password", json={"current_password": PW, "new_password": "short1"})
    assert weak.status_code == 422 and weak.json()["error"]["code"] == "weak_password"
    same = client.post("/api/v1/auth/change-password", json={"current_password": PW, "new_password": PW})
    assert same.status_code == 422


def test_forced_password_change_blocks_api_until_changed(client, test_db):
    u = _user(test_db)
    u.must_change_password = True
    test_db.commit()
    me = login(client, "acct@example.com", PW)
    assert me.status_code == 200 and me.json()["must_change_password"] is True
    blocked = client.get("/api/v1/tasks")
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "password_change_required"
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.post("/api/v1/auth/change-password",
                       json={"current_password": PW, "new_password": NEW}).status_code == 204
    assert client.get("/api/v1/tasks").status_code != 403


# ------------------------------------------------------------------- reset
def test_forgot_password_does_not_enumerate(client, test_db):
    _user(test_db)
    a = client.post("/api/v1/auth/forgot-password", json={"email": "acct@example.com"})
    b = client.post("/api/v1/auth/forgot-password", json={"email": "ghost@example.com"})
    assert a.status_code == b.status_code == 202 and a.json() == b.json()
    assert test_db.query(PasswordResetToken).count() == 1


def test_reset_password_flow_single_use(client, test_db, monkeypatch):
    user = _user(test_db)
    sent = {}
    from app.services import email_sender
    monkeypatch.setattr(email_sender, "send_email", lambda **kw: sent.update(kw))
    client.post("/api/v1/auth/forgot-password", json={"email": "acct@example.com"})
    token = sent["body"].split("token=")[1].split()[0]

    # token only stored hashed
    assert test_db.query(PasswordResetToken).filter_by(token_hash=token).count() == 0
    ok = client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": NEW})
    assert ok.status_code == 204
    reuse = client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": NEW + "x"})
    assert reuse.status_code == 400 and reuse.json()["error"]["code"] == "invalid_reset_token"
    assert login(client, user.email, NEW).status_code == 200


def test_reset_rejects_unknown_and_expired(client, test_db):
    _user(test_db)
    assert client.post("/api/v1/auth/reset-password",
                       json={"token": "x" * 40, "new_password": NEW}).status_code == 400
    from datetime import timedelta
    from app.db.base import utcnow
    from app.core.security import hash_token
    u = test_db.query(User).filter_by(email="acct@example.com").one()
    test_db.add(PasswordResetToken(user_id=u.id, token_hash=hash_token("e" * 40),
                                   expires_at=utcnow() - timedelta(minutes=1)))
    test_db.commit()
    assert client.post("/api/v1/auth/reset-password",
                       json={"token": "e" * 40, "new_password": NEW}).status_code == 400


# --------------------------------------------------------------------- MFA
def _enable_mfa(client):
    setup = client.post("/api/v1/auth/mfa/setup").json()
    assert setup["qr_svg_data_uri"].startswith("data:image/svg+xml")
    codes = client.post("/api/v1/auth/mfa/enable", json={"code": pyotp.TOTP(setup["secret"]).now()}).json()
    return setup["secret"], codes["recovery_codes"]


def test_mfa_login_flow_and_recovery_code(client, test_db):
    _user(test_db)
    login(client, "acct@example.com", PW)
    secret, recovery = _enable_mfa(client)
    assert len(recovery) == 10
    stored = test_db.query(User).filter_by(email="acct@example.com").one()
    assert secret not in (stored.totp_secret_enc or "")        # encrypted at rest

    fresh = TestClient(client.app)
    need = login(fresh, "acct@example.com", PW)
    assert need.status_code == 401 and need.json()["error"]["code"] == "mfa_required"
    assert fresh.get("/api/v1/auth/me").status_code == 401     # no session issued yet

    bad = fresh.post("/api/v1/auth/login", json={"email": "acct@example.com", "password": PW, "otp_code": "000000"})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "invalid_otp"

    good = fresh.post("/api/v1/auth/login", json={
        "email": "acct@example.com", "password": PW, "otp_code": pyotp.TOTP(secret).now()})
    assert good.status_code == 200 and good.json()["mfa_enabled"] is True

    rc = TestClient(client.app)
    use = rc.post("/api/v1/auth/login", json={"email": "acct@example.com", "password": PW, "otp_code": recovery[0]})
    assert use.status_code == 200
    again = TestClient(client.app).post("/api/v1/auth/login",
                                        json={"email": "acct@example.com", "password": PW, "otp_code": recovery[0]})
    assert again.status_code == 401                              # single use


def test_mfa_wrong_codes_count_toward_lockout(client, test_db):
    _user(test_db)
    login(client, "acct@example.com", PW)
    _enable_mfa(client)
    c = TestClient(client.app)
    for _ in range(5):
        c.post("/api/v1/auth/login", json={"email": "acct@example.com", "password": PW, "otp_code": "111111"})
    locked = c.post("/api/v1/auth/login", json={"email": "acct@example.com", "password": PW, "otp_code": "111111"})
    assert locked.json()["error"]["code"] == "account_state"


def test_mfa_disable_requires_password_and_code(client, test_db):
    _user(test_db)
    login(client, "acct@example.com", PW)
    secret, _ = _enable_mfa(client)
    assert client.post("/api/v1/auth/mfa/disable",
                       json={"password": "wrong", "code": pyotp.TOTP(secret).now()}).status_code == 400
    assert client.post("/api/v1/auth/mfa/disable",
                       json={"password": PW, "code": pyotp.TOTP(secret).now()}).status_code == 204
    assert client.get("/api/v1/auth/me").json()["mfa_enabled"] is False


def test_admin_can_reset_users_mfa(client, test_db):
    user = _user(test_db)
    login(client, "acct@example.com", PW)
    _enable_mfa(client)
    admin = TestClient(client.app)
    assert login(admin, "admin@interdec.com", "DecOps!2026").status_code == 200
    r = admin.post(f"/api/v1/users/{user.id}/reset-mfa")
    assert r.status_code == 200
    test_db.refresh(user)
    assert user.totp_enabled is False and user.totp_secret_enc is None
    assert client.get("/api/v1/auth/me").status_code == 401     # sessions revoked
    assert login(TestClient(client.app), "acct@example.com", PW).status_code == 200


# ---------------------------------------------------------------- sessions
def test_sessions_list_and_revoke(client, test_db):
    _user(test_db)
    login(client, "acct@example.com", PW)
    second = TestClient(client.app)
    login(second, "acct@example.com", PW)
    sessions = client.get("/api/v1/auth/sessions").json()
    assert len(sessions) == 2 and sum(s["current"] for s in sessions) == 1
    other = next(s for s in sessions if not s["current"])
    assert client.delete(f"/api/v1/auth/sessions/{other['id']}").status_code == 204
    assert second.get("/api/v1/auth/me").status_code == 401
    assert client.delete(f"/api/v1/auth/sessions/{other['id']}").status_code == 404
    assert client.post("/api/v1/auth/sessions/revoke-others").status_code == 204


def test_cannot_revoke_someone_elses_session(client, test_db):
    _user(test_db)
    _user(test_db, email="other@example.com")
    victim = TestClient(client.app)
    login(victim, "other@example.com", PW)
    sid = victim.get("/api/v1/auth/sessions").json()[0]["id"]
    login(client, "acct@example.com", PW)
    assert client.delete(f"/api/v1/auth/sessions/{sid}").status_code == 404
    assert victim.get("/api/v1/auth/me").status_code == 200


# ------------------------------------------------------------------- audit
def test_audit_viewer_permissions_and_scoping(client, test_db):
    make_user(test_db, email="aud@example.com", password=PW, role_names=["Read-Only Auditor"])
    make_user(test_db, email="sys@example.com", password=PW, role_names=["System Administrator"])
    make_user(test_db, email="mem@example.com", password=PW)
    for who in ("aud", "sys", "mem"):
        login(TestClient(client.app), f"{who}@example.com", PW)
    test_db.add(AuditEvent(action="task.created", resource_type="task", change_summary="business thing"))
    test_db.commit()

    aud = TestClient(client.app); login(aud, "aud@example.com", PW)
    r = aud.get("/api/v1/audit/events?page_size=200")
    assert r.status_code == 200
    actions = {e["action"] for e in r.json()["items"]}
    assert "task.created" in actions and "auth.login" in actions

    sysadm = TestClient(client.app); login(sysadm, "sys@example.com", PW)
    sys_actions = {e["action"] for e in sysadm.get("/api/v1/audit/events?page_size=200").json()["items"]}
    assert "auth.login" in sys_actions and "task.created" not in sys_actions

    mem = TestClient(client.app); login(mem, "mem@example.com", PW)
    assert mem.get("/api/v1/audit/events").status_code == 404
    assert TestClient(client.app).get("/api/v1/audit/events").status_code == 401


def test_audit_filter_and_csv_export_neutralises_formulas(client, test_db):
    make_user(test_db, email="aud@example.com", password=PW, role_names=["Read-Only Auditor"])
    test_db.add(AuditEvent(action="task.created", resource_type="task", change_summary="=HYPERLINK(\"x\")"))
    test_db.commit()
    aud = TestClient(client.app); login(aud, "aud@example.com", PW)
    only = aud.get("/api/v1/audit/events?action=task.").json()
    assert only["total"] == 1
    csv_text = aud.get("/api/v1/audit/events/export?action=task.").text
    assert "'=HYPERLINK" in csv_text and ",=HYPERLINK" not in csv_text


def test_secrets_never_in_audit_metadata(client, test_db):
    _user(test_db)
    login(client, "acct@example.com", PW)
    secret, recovery = _enable_mfa(client)
    blob = " ".join(str(e.metadata_json) + str(e.change_summary) for e in test_db.query(AuditEvent))
    assert secret not in blob and recovery[0] not in blob and PW not in blob


# ------------------------------------------------------------ rate limiting
def test_login_rate_limited_per_ip(test_db):
    from app.api.deps import get_db

    cfg = Settings(environment="staging", database_url="sqlite://", rate_limit_enabled=True,
                   outbox_worker_enabled=False)
    app = create_app(override_settings=cfg)
    app.dependency_overrides[get_db] = lambda: (yield test_db)
    with TestClient(app) as c:
        codes = [c.post("/api/v1/auth/forgot-password", json={"email": "x@y.co"}).status_code
                 for _ in range(7)]
        assert codes[:5] == [202] * 5 and codes[5:] == [429, 429]
        r = c.post("/api/v1/auth/forgot-password", json={"email": "x@y.co"})
        assert r.status_code == 429 and "retry-after" in r.headers
        # unrelated endpoints are not limited
        assert c.get("/api/v1/health").status_code == 200
