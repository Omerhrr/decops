#!/usr/bin/env python3
"""Phase 10 launch orchestrator: production launch drill for DecOps.

Executes the launch objectives as a repeatable, audited sequence:
  1. Preflight: configuration and database readiness checks.
  2. Accounts: provision approved user accounts from a manifest (idempotent).
  3. Register: import the validated task register through the Phase 8
     pipeline (validate, commit, retry safe).
  4. Smoke: end-to-end HTTP smoke tests per role against a running API.
  5. Report: JSON launch report under backend/var/launch/.

Usage (from backend/):
  uv run python ../scripts/launch_phase10.py [--base-url http://localhost:8000]

Passwords: provide a CSV (email,password) via --passwords-csv, otherwise
strong random passwords are generated and written to
backend/var/launch_credentials.csv (0600, git ignored) and printed once.
Rotate at first login per the runbook pre-launch checklist.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import secrets
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy import func, select, text

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings  # noqa: E402
from app.db.base import utcnow  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.domain.csv_import import auto_map_headers  # noqa: E402
from app.models import (  # noqa: E402
    AccountStatus,
    DepartmentMembership,
    ImportJob,
    MembershipRole,
    Role,
    Task,
    User,
)
from app.seeds.rbac_matrix import ROLE_MATRIX  # noqa: E402
from app.services import department_service, import_service, user_admin_service  # noqa: E402

REPO_ROOT = BACKEND_DIR.parent
DEFAULT_ACCOUNTS = REPO_ROOT / "docs" / "launch" / "accounts_manifest.csv"
DEFAULT_REGISTER = REPO_ROOT / "docs" / "launch" / "task_register.csv"
CREDS_PATH = BACKEND_DIR / "var" / "launch_credentials.csv"
REPORT_DIR = BACKEND_DIR / "var" / "launch"

LEAD_ROLES = {"Department Lead"}


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

def preflight(db) -> dict:
    """Configuration plus database readiness. Fatal failures abort the drill."""
    cfg = get_settings()
    checks: list[dict] = []
    warnings: list[str] = []

    def check(name: str, ok: bool, detail: str = "", *, fatal: bool = True) -> None:
        checks.append({"check": name, "ok": ok, "detail": detail, "fatal": fatal})

    if cfg.is_production:
        check("session_secret_rotated", "change-me" not in cfg.session_secret_key,
              "session secret must not be the default value")
        check("secure_cookies", cfg.secure_cookies, "DECOPS_SECURE_COOKIES=true behind TLS")
        check("debug_disabled", not cfg.debug, "DECOPS_DEBUG=false")
    else:
        warnings.append(
            f"environment='{cfg.environment}'; running the drill outside the "
            "production posture. Set DECOPS_ENVIRONMENT=production for the real rollout."
        )
        check("database_configured", bool(cfg.database_url), cfg.database_url.split("://")[0])
        check("session_secret_rotated", "change-me" not in cfg.session_secret_key,
              "session secret must not be the default value")

    user_count = db.scalar(select(func.count()).select_from(User))
    check("database_reachable", user_count is not None, f"users={user_count}")
    role_names = {r for (r,) in db.execute(select(Role.name)).all()}
    missing_roles = sorted(set(ROLE_MATRIX) - role_names)
    check("rbac_seeded", not missing_roles,
          f"missing={missing_roles}" if missing_roles else "9 system roles present")
    admin = user_admin_service.get_by_email(db, cfg.seed_admin_email)
    check("initial_admin_present", admin is not None and admin.account_status == AccountStatus.active,
          cfg.seed_admin_email)
    try:
        version_row = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        check("migrations_applied", bool(version_row), f"head={version_row}")
    except Exception as exc:
        check("migrations_applied", False, f"alembic_version unreadable: {exc}")

    failed = [c for c in checks if not c["ok"] and c["fatal"]]
    return {"ok": not failed, "checks": checks, "warnings": warnings}


# ---------------------------------------------------------------------------
# Approved accounts
# ---------------------------------------------------------------------------

def load_or_generate_passwords(accounts: list[dict], passwords_csv: Path | None) -> dict[str, str]:
    """Resolve per-account passwords. The credentials file is the stable source
    across drill re-runs: existing entries are never regenerated."""
    passwords: dict[str, str] = {}
    if passwords_csv:
        with open(passwords_csv, newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                if row.get("email") and row.get("password"):
                    passwords[row["email"].strip().lower()] = row["password"]
    if CREDS_PATH.exists():
        with open(CREDS_PATH, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row.get("email") and row.get("temporary_password"):
                    passwords.setdefault(row["email"].strip().lower(), row["temporary_password"])
    missing = [a["email"] for a in accounts if a["email"] not in passwords]
    for email in missing:
        passwords[email] = "D" + secrets.token_urlsafe(12) + "!7"
    if missing:
        CREDS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CREDS_PATH, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["email", "temporary_password"])
            for email in missing:
                writer.writerow([email, passwords[email]])
        CREDS_PATH.chmod(0o600)  # owner-only credentials at rest
        print(f"  credentials written to {CREDS_PATH} (chmod 600); rotate at first login")
    return passwords


def provision_accounts(db, manifest_path: Path, passwords_csv: Path | None) -> dict:
    """Create approved accounts, role assignments and department memberships."""
    admin = user_admin_service.get_by_email(db, get_settings().seed_admin_email)
    with open(manifest_path, newline="", encoding="utf-8-sig") as fh:
        rows = [r for r in csv.DictReader(fh) if r.get("email")]

    passwords = load_or_generate_passwords(rows, passwords_csv)
    created, skipped, problems = [], [], []
    role_cache = {r.name: r for r in db.scalars(select(Role)).all()}
    provisioned_passwords: dict[str, str] = {}

    for row in rows:
        email = row["email"].strip().lower()
        try:
            user = user_admin_service.get_by_email(db, email)
            if user is None:
                role_names = [n.strip() for n in row["roles"].split(";") if n.strip()]
                unknown = [n for n in role_names if n not in role_cache]
                if unknown:
                    raise user_admin_service.UserAdminError(
                        f"Unknown roles: {unknown}", code="role_not_found")
                user = user_admin_service.create_user(
                    db, actor=admin, email=email, full_name=row["full_name"].strip(),
                    employee_code=row["employee_code"].strip(),
                    password=passwords[email],
                    role_ids=[role_cache[n].id for n in role_names],
                )
                created.append({"email": email, "roles": role_names})
            else:
                skipped.append({"email": email, "reason": "already provisioned"})
            provisioned_passwords[email] = passwords[email]

            dept_name = (row.get("department") or "").strip()
            if dept_name:
                dept = department_service.get_by_name(db, dept_name)
                if dept is None:
                    problems.append({"email": email, "problem": f"department '{dept_name}' not found"})
                else:
                    existing = db.scalar(select(DepartmentMembership).where(
                        DepartmentMembership.department_id == dept.id,
                        DepartmentMembership.user_id == user.id))
                    if existing is None:
                        is_lead = bool(LEAD_ROLES & {n.strip() for n in row["roles"].split(";")})
                        department_service.add_member(
                            db, actor=admin, department=dept, user=user,
                            membership_role=MembershipRole.lead if is_lead else MembershipRole.member)
        except user_admin_service.UserAdminError as exc:
            problems.append({"email": email, "problem": f"{exc.code}: {exc.message}"})

    db.commit()
    return {"manifest": str(manifest_path), "created": created, "skipped": skipped,
            "problems": problems, "total_in_manifest": len(rows),
            "passwords": provisioned_passwords}


# ---------------------------------------------------------------------------
# Validated task register import (the real Phase 8 pipeline)
# ---------------------------------------------------------------------------

def import_register(db, register_path: Path) -> dict:
    admin = user_admin_service.get_by_email(db, get_settings().seed_admin_email)

    # Retry-safe pre-check: when every register Task ID already exists in
    # DecOps, the register was imported in a previous run; skip without
    # creating a redundant job.
    with open(register_path, newline="", encoding="utf-8-sig") as fh:
        legacy_ids = [r["Task ID"].strip() for r in csv.DictReader(fh) if r.get("Task ID")]
    existing = set(db.scalars(select(Task.legacy_external_id).where(
        Task.legacy_external_id.in_(legacy_ids))).all() if legacy_ids else [])
    if legacy_ids and set(legacy_ids) <= existing:
        total = db.scalar(select(func.count()).select_from(ImportJob))
        return {"register": str(register_path), "skipped": "already_imported",
                "legacy_ids_present": len(legacy_ids), "import_jobs_total": total}

    from starlette.datastructures import UploadFile

    data = register_path.read_bytes()
    upload = UploadFile(file=io.BytesIO(data), filename=register_path.name)

    text_content = data.decode("utf-8-sig")
    headers = next(csv.reader(io.StringIO(text_content)))
    mapping = auto_map_headers(headers)

    job = import_service.create_import_job(db, actor=admin, upload=upload, mapping=mapping)
    db.commit()

    import_service.validate_job(db, job)
    db.commit()
    report = import_service.load_report(job)
    counts = report.get("counts", {})

    commit_result: dict = {}
    if counts.get("failed", 0) == 0:
        try:
            commit_result = import_service.commit_import(db, actor=admin, job=job)
            db.commit()
        except Exception as exc:
            db.rollback()
            commit_result = {"error": str(exc)}
    else:
        commit_result = {"error": f"register has failed rows: {counts}"}

    jobs = db.scalar(select(func.count()).select_from(ImportJob))
    return {
        "register": str(register_path),
        "job_id": str(job.id),
        "row_counts": counts,
        "commit": commit_result,
        "import_jobs_total": jobs,
    }


# ---------------------------------------------------------------------------
# HTTP smoke tests (role appropriate surfaces, with negative assertions)
# ---------------------------------------------------------------------------

SMOKE_MATRIX = {
    "Company Administrator": [("/api/v1/auth/me", 200), ("/api/v1/tasks", 200),
                              ("/api/v1/imports", 200), ("/api/v1/users", 200)],
    "System Administrator": [("/api/v1/auth/me", 200),
                             ("/api/v1/imports", 404)],  # no business content (spec)
    "Management": [("/api/v1/auth/me", 200), ("/api/v1/dashboard/summary", 200),
                   ("/api/v1/tasks", 200), ("/api/v1/reports/task-completion", 200)],
    "Accountable PM": [("/api/v1/auth/me", 200), ("/api/v1/tasks", 200),
                       ("/api/v1/dashboard/summary", 200)],
    "Supporting PM": [("/api/v1/auth/me", 200), ("/api/v1/dashboard/my-tasks", 200)],
    "Department Lead": [("/api/v1/auth/me", 200), ("/api/v1/dashboard/summary", 200),
                        ("/api/v1/dashboard/my-tasks", 200),
                        ("/api/v1/departments", 404)],  # manage-only surface stays blocked
    "Department Member": [("/api/v1/auth/me", 200), ("/api/v1/dashboard/my-tasks", 200)],
    "Approver": [("/api/v1/auth/me", 200), ("/api/v1/tasks", 200)],
    "Read-Only Auditor": [("/api/v1/auth/me", 200), ("/api/v1/tasks", 200),
                          ("/api/v1/reports/task-completion", 404),  # no reports.view (spec)
                          ("/api/v1/users", 404)],
}


def smoke_tests(base_url: str, creds: dict[str, str]) -> dict:
    results: list[dict] = []
    client = httpx.Client(base_url=base_url, timeout=15.0, follow_redirects=False)

    try:
        health = client.get("/api/v1/health")
        health_ok = health.status_code == 200 and health.json().get("status") == "ok"
    except Exception as exc:
        return {"ok": False, "results": [{"account": "health", "ok": False, "detail": str(exc)}]}

    for email, password in creds.items():
        resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        if resp.status_code != 200:
            results.append({"account": email, "ok": False,
                            "detail": f"login {resp.status_code}: {resp.text[:120]}"})
            continue
        me = client.get("/api/v1/auth/me").json()
        role_names = [r.get("name") for r in me.get("roles", [])]
        matrix_key = next((k for k in SMOKE_MATRIX if k in role_names), "Company Administrator")
        for path, expected in SMOKE_MATRIX[matrix_key]:
            try:
                probe = client.get(path)
                passed = probe.status_code == expected
                results.append({"account": email, "role": matrix_key, "path": path,
                                "expected": expected, "status": probe.status_code, "ok": passed,
                                "detail": "" if passed else probe.text[:120]})
            except Exception as exc:
                results.append({"account": email, "role": matrix_key, "path": path,
                                "expected": expected, "status": 0, "ok": False, "detail": str(exc)})
        client.post("/api/v1/auth/logout")

    passed_all = health_ok and all(r["ok"] for r in results)
    return {"ok": passed_all, "health_ok": health_ok, "results": results}


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(payload: dict) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    path = REPORT_DIR / f"launch_report-{stamp}.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="DecOps Phase 10 launch orchestrator")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--accounts", type=Path, default=DEFAULT_ACCOUNTS)
    parser.add_argument("--register", type=Path, default=DEFAULT_REGISTER)
    parser.add_argument("--passwords-csv", type=Path, default=None)
    parser.add_argument("--skip-import", action="store_true")
    parser.add_argument("--skip-smoke", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    payload: dict = {"started_at": utcnow().isoformat(), "base_url": args.base_url}
    exit_code = 0
    try:
        print("== Phase 10 launch drill ==")

        print("[1/4] Preflight")
        pre = preflight(db)
        payload["preflight"] = pre
        for c in pre["checks"]:
            print(f"  {'PASS' if c['ok'] else 'FAIL'}  {c['check']}  {c['detail']}")
        for w in pre["warnings"]:
            print(f"  WARN  {w}")
        if not pre["ok"]:
            print("Preflight failed; aborting launch drill.")
            payload["aborted"] = "preflight"
            return 2

        print("[2/4] Approved accounts")
        accounts = provision_accounts(db, args.accounts, args.passwords_csv)
        launch_passwords = accounts.pop("passwords", {})  # never persisted to the report
        payload["accounts"] = accounts
        print(f"  created={len(accounts['created'])} skipped={len(accounts['skipped'])} "
              f"problems={len(accounts['problems'])}")

        print("[3/4] Validated task register import")
        if args.skip_import:
            payload["import"] = {"skipped": True}
            print("  skipped (--skip-import)")
        else:
            imp = import_register(db, args.register)
            payload["import"] = imp
            if imp.get("skipped"):
                print(f"  skipped: {imp['skipped']} "
                      f"({imp.get('legacy_ids_present')} register IDs already in DecOps)")
            else:
                print(f"  rows={imp['row_counts']} commit={imp['commit'].get('summary', imp['commit'])}")

        print("[4/4] Smoke tests")
        if args.skip_smoke:
            payload["smoke"] = {"skipped": True}
            print("  skipped (--skip-smoke)")
        else:
            creds = launch_passwords or load_or_generate_passwords(
                [{"email": r["email"].strip().lower()} for r in csv.DictReader(
                    open(args.accounts, newline="", encoding="utf-8-sig"))], args.passwords_csv)
            smoke = smoke_tests(args.base_url, creds)
            payload["smoke"] = smoke
            failures = [r for r in smoke["results"] if not r["ok"]]
            print(f"  health={'ok' if smoke.get('health_ok') else 'DOWN'} "
                  f"probes={len(smoke['results'])} failures={len(failures)}")
            for f in failures[:10]:
                print(f"    FAIL {f['account']} {f.get('path', '')} -> {f.get('status')} {f['detail'][:100]}")

        smoke_results = payload.get("smoke", {}).get("results", [])
        failed_probe = any(not r.get("ok") for r in smoke_results)
        exit_code = 0 if not failed_probe else 1
    finally:
        payload["finished_at"] = utcnow().isoformat()
        report_path = write_report(payload)
        print(f"Launch report: {report_path}")
        db.close()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
