"""Settings suite: organization settings, PDF design, appearance preferences,
custom role administration, PDF exports, and dashboard chart payload."""

import re

from sqlalchemy import select

from app.models import AuditEvent, Role, User
from tests.conftest import login, make_user


def _admin(client):
    assert login(client, "admin@interdec.com", "DecOps!2026").status_code == 200


def _member(client, db, email="member@x.com"):
    make_user(db, email=email, role_names=["Department Member"])
    assert login(client, email, "Secret!1234").status_code == 200


# ---------------------------------------------------------------------------
# Organization settings
# ---------------------------------------------------------------------------

def test_org_settings_defaults_visible_to_any_user(client, test_db):
    _member(client, test_db)
    r = client.get("/api/v1/settings/org")
    assert r.status_code == 200
    assert r.json()["org_name"] == "Interdec"


def test_org_settings_update_requires_manage_permission(client, test_db):
    _member(client, test_db)
    assert client.put("/api/v1/settings/org", json={"org_name": "X"}).status_code == 404


def test_org_settings_update_persists_and_audits(client, test_db):
    _admin(client)
    r = client.put("/api/v1/settings/org", json={"org_name": "Interdec Industries"})
    assert r.status_code == 200
    assert r.json()["org_name"] == "Interdec Industries"
    actions = [e.action for e in test_db.scalars(select(AuditEvent)).all()]
    assert "settings.updated" in actions


def test_org_settings_reject_blank_name(client, test_db):
    _admin(client)
    r = client.put("/api/v1/settings/org", json={"org_name": "   "})
    assert r.status_code == 422 or r.status_code == 400


# ---------------------------------------------------------------------------
# PDF design settings
# ---------------------------------------------------------------------------

def test_pdf_design_defaults_and_update(client, test_db):
    _admin(client)
    r = client.get("/api/v1/settings/pdf-design")
    assert r.status_code == 200
    assert r.json()["paper_size"] == "A4"

    r = client.put("/api/v1/settings/pdf-design", json={
        "paper_size": "Letter",
        "orientation": "landscape",
        "accent_color": "#1d4ed8",
        "table_style": "bordered",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["paper_size"] == "Letter"
    assert body["accent_color"] == "#1D4ED8"

    r = client.get("/api/v1/settings/pdf-design")
    assert r.json()["orientation"] == "landscape"


def test_pdf_design_rejects_bad_values(client, test_db):
    _admin(client)
    assert client.put(
        "/api/v1/settings/pdf-design", json={"paper_size": "A3"}
    ).status_code in (400, 422)
    assert client.put(
        "/api/v1/settings/pdf-design", json={"accent_color": "blue"}
    ).status_code in (400, 422)
    assert client.put(
        "/api/v1/settings/pdf-design", json={"font_size_pt": 20}
    ).status_code in (400, 422)


def test_pdf_design_member_blocked(client, test_db):
    _member(client, test_db)
    assert client.get("/api/v1/settings/pdf-design").status_code == 404


def test_pdf_preview_renders_pdf_without_persisting(client, test_db):
    _admin(client)
    r = client.post("/api/v1/settings/pdf-preview", json={
        "design": {"accent_color": "#b91c1c", "paper_size": "Letter"}
    })
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"
    stored = client.get("/api/v1/settings/pdf-design").json()
    assert stored["accent_color"] != "#B91C1C"
    assert stored["paper_size"] == "A4"


# ---------------------------------------------------------------------------
# Appearance preferences
# ---------------------------------------------------------------------------

def test_preferences_roundtrip(client, test_db):
    _member(client, test_db)
    r = client.get("/api/v1/me/preferences")
    assert r.status_code == 200
    assert r.json() == {"theme_mode": "system", "accent_color": "emerald", "font_family": "inter"}

    r = client.put("/api/v1/me/preferences", json={
        "theme_mode": "dark", "accent_color": "violet", "font_family": "serif",
    })
    assert r.status_code == 200
    assert r.json()["theme_mode"] == "dark"

    r = client.get("/api/v1/auth/me")
    assert r.json()["preferences"]["accent_color"] == "violet"


def test_preferences_reject_unknown_values(client, test_db):
    _member(client, test_db)
    assert client.put(
        "/api/v1/me/preferences", json={"theme_mode": "navy"}
    ).status_code in (400, 422)
    assert client.put(
        "/api/v1/me/preferences", json={"accent_color": "#ff0000"}
    ).status_code in (400, 422)


# ---------------------------------------------------------------------------
# Custom role administration
# ---------------------------------------------------------------------------

def test_create_custom_role_and_effective_permissions(client, test_db):
    _admin(client)
    r = client.post("/api/v1/roles", json={
        "name": "Reporting Analyst",
        "description": "Reads management reports",
        "permissions": ["reports.view", "dashboards.view"],
    })
    assert r.status_code == 201
    role = r.json()
    assert role["is_system_role"] is False
    assert sorted(role["permissions"]) == ["dashboards.view", "reports.view"]

    make_user(test_db, email="analyst@x.com", role_names=["Reporting Analyst"])
    c2_login = login(client, "analyst@x.com", "Secret!1234")
    assert c2_login.status_code == 200
    assert "reports.view" in c2_login.json()["permissions"]


def test_create_role_rejects_duplicate_name_and_unknown_permission(client, test_db):
    _admin(client)
    assert client.post("/api/v1/roles", json={
        "name": "Management", "permissions": [],
    }).status_code == 409
    r = client.post("/api/v1/roles", json={
        "name": "Ghost", "permissions": ["not.a.permission"],
    })
    assert r.status_code in (400, 422)


def test_system_roles_are_read_only(client, test_db):
    _admin(client)
    roles = client.get("/api/v1/roles").json()["items"]
    system = next(r for r in roles if r["is_system_role"])
    r = client.patch(f"/api/v1/roles/{system['id']}", json={"name": "Renamed"})
    assert r.status_code in (400, 422)
    assert client.delete(f"/api/v1/roles/{system['id']}").status_code in (400, 422)


def test_update_and_delete_custom_role(client, test_db):
    _admin(client)
    role_id = client.post("/api/v1/roles", json={
        "name": "Contractor", "permissions": ["comments.create"],
    }).json()["id"]

    r = client.patch(f"/api/v1/roles/{role_id}", json={
        "description": "Limited contractor access", "permissions": ["profile.read"],
    })
    assert r.status_code == 200
    assert r.json()["permissions"] == ["profile.read"]

    # Assigned roles cannot be deleted
    make_user(test_db, email="contractor@x.com", role_names=["Contractor"])
    assert client.delete(f"/api/v1/roles/{role_id}").status_code == 409

    # Unassigned roles can be deleted
    spare_id = client.post("/api/v1/roles", json={
        "name": "Spare Role", "permissions": [],
    }).json()["id"]
    assert client.delete(f"/api/v1/roles/{spare_id}").status_code == 204
    names = [r["name"] for r in client.get("/api/v1/roles").json()["items"]]
    assert "Spare Role" not in names


def test_role_administration_gated(client, test_db):
    make_user(test_db, email="mgr@x.com", role_names=["Management"])
    login(client, "mgr@x.com", "Secret!1234")
    assert client.get("/api/v1/roles").status_code == 404
    assert client.post("/api/v1/roles", json={
        "name": "Nope", "permissions": [],
    }).status_code == 404


# ---------------------------------------------------------------------------
# PDF exports
# ---------------------------------------------------------------------------

def test_pdf_export_register_returns_pdf(client, test_db):
    make_user(test_db, email="auditor@x.com", role_names=["Read-Only Auditor"])
    login(client, "auditor@x.com", "Secret!1234")
    r = client.post("/api/v1/reports/exports", json={
        "export_type": "task_register", "format": "pdf",
    })
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"
    assert "attachment" in r.headers["content-disposition"]
    assert ".pdf" in r.headers["content-disposition"]


def test_pdf_export_completion_and_workload(client, test_db):
    make_user(test_db, email="auditor2@x.com", role_names=["Read-Only Auditor"])
    login(client, "auditor2@x.com", "Secret!1234")
    for export_type in ("task_completion", "department_workload"):
        r = client.post("/api/v1/reports/exports", json={
            "export_type": export_type, "format": "pdf",
        })
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"


def test_csv_export_still_works(client, test_db):
    make_user(test_db, email="auditor3@x.com", role_names=["Read-Only Auditor"])
    login(client, "auditor3@x.com", "Secret!1234")
    r = client.post("/api/v1/reports/exports", json={
        "export_type": "task_register", "format": "csv",
    })
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]


def test_pdf_export_applies_custom_design(client, test_db):
    _admin(client)
    client.put("/api/v1/settings/pdf-design", json={
        "accent_color": "#7c3aed", "paper_size": "Letter", "orientation": "landscape",
    })
    make_user(test_db, email="auditor4@x.com", role_names=["Read-Only Auditor"])
    login(client, "auditor4@x.com", "Secret!1234")
    r = client.post("/api/v1/reports/exports", json={
        "export_type": "task_register", "format": "pdf",
    })
    assert r.status_code == 200
    assert len(r.content) > 1000


# ---------------------------------------------------------------------------
# Dashboard charts payload
# ---------------------------------------------------------------------------

def test_dashboard_summary_includes_charts(client, test_db):
    make_user(test_db, email="chartuser@x.com", role_names=["Management"])
    login(client, "chartuser@x.com", "Secret!1234")
    r = client.get("/api/v1/dashboard/summary")
    assert r.status_code == 200
    charts = r.json()["charts"]
    assert len(charts["trend"]) == 8
    assert set(charts["trend"][0]) == {"week_start", "created", "completed"}
    assert isinstance(charts["by_priority"], dict)
    assert isinstance(charts["by_department"], list)


def test_week_starts_are_mondays(client, test_db):
    make_user(test_db, email="chartuser2@x.com", role_names=["Management"])
    login(client, "chartuser2@x.com", "Secret!1234")
    charts = client.get("/api/v1/dashboard/summary").json()["charts"]
    for point in charts["trend"]:
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", point["week_start"])
