"""Deployment hardening: production config gate, URL normalization, request guards."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

GOOD = dict(
    environment="production", database_url="postgresql://u:p@h/d",
    session_secret_key="k" * 48, secure_cookies=True, debug=False,
    seed_admin_password="Str0ng-Passw0rd!", trusted_origins=["https://ops.example.com"],
)


def test_production_rejects_insecure_defaults():
    with pytest.raises(RuntimeError) as exc:
        Settings(environment="production").assert_production_ready()
    msg = str(exc.value)
    for needle in ("SESSION_SECRET_KEY", "SECURE_COOKIES", "DEBUG", "PostgreSQL", "ADMIN_PASSWORD", "TRUSTED_ORIGINS"):
        assert needle in msg


def test_production_accepts_hardened_config():
    cfg = Settings(**GOOD)
    cfg.assert_production_ready()
    assert cfg.database_url.startswith("postgresql+psycopg://")
    assert cfg.should_seed_demo_data is False


def test_demo_data_defaults_on_outside_production():
    assert Settings(environment="development").should_seed_demo_data is True
    assert Settings(environment="production", seed_demo_data=True).should_seed_demo_data is True


def _client(**kw):
    cfg = Settings(environment="testing", database_url="sqlite://", **kw)
    return TestClient(create_app(override_settings=cfg))


def test_cross_origin_unsafe_request_blocked():
    with _client(trusted_origins=["https://ops.example.com"]) as c:
        bad = c.post("/api/v1/health", headers={"Origin": "https://evil.example"})
        assert bad.status_code == 403
        ok = c.post("/api/v1/health", headers={"Origin": "https://ops.example.com"})
        assert ok.status_code == 405  # passed the guard; POST just is not allowed here


def test_oversized_body_rejected():
    with _client(max_request_bytes=1000) as c:
        r = c.post("/api/v1/health", content=b"x" * 5000)
        assert r.status_code == 413
