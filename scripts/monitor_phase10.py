#!/usr/bin/env python3
"""Phase 10 early-usage monitor: health, adoption and alert snapshot.

Checks (per runbook section 5):
  - Liveness: GET /api/v1/health
  - Adoption: active users, logins today/7d, active sessions
  - Register health: tasks by status, overdue, created/completed 7d
  - Delivery pipeline: outbox pending / permanent_failure backlog
  - Security: auth.login_failed bursts (15 minute window)

Usage:
  python3 scripts/monitor_phase10.py [--base-url http://localhost:8000] [--json]
Snapshots are appended to backend/var/monitoring/ (last 20 kept).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from sqlalchemy import func, select

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings  # noqa: E402
from app.db.base import utcnow  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models import AuditEvent, ImportJob, OutboxEvent, OutboxStatus, Task, User, UserSession  # noqa: E402

SNAPSHOT_DIR = BACKEND_DIR / "var" / "monitoring"
LOGIN_FAILED_ALERT_THRESHOLD = 10  # per 15 minutes (runbook section 5)
KEEP_SNAPSHOTS = 20


def gather(db) -> dict:
    now = utcnow()
    day_ago = now - timedelta(hours=24)
    week_ago = now - timedelta(days=7)
    quarter_ago = now - timedelta(minutes=15)

    users_total = db.scalar(select(func.count()).select_from(User)) or 0
    users_active = db.scalar(
        select(func.count()).select_from(User).where(User.account_status == "active")) or 0
    sessions_active = db.scalar(
        select(func.count()).select_from(UserSession).where(
            UserSession.revoked_at.is_(None), UserSession.expires_at > now)) or 0

    logins_24h = db.scalar(
        select(func.count()).select_from(AuditEvent).where(
            AuditEvent.action == "auth.login", AuditEvent.occurred_at >= day_ago)) or 0
    logins_7d = db.scalar(
        select(func.count()).select_from(AuditEvent).where(
            AuditEvent.action == "auth.login", AuditEvent.occurred_at >= week_ago)) or 0
    distinct_users_7d = db.scalar(
        select(func.count(func.distinct(AuditEvent.actor_user_id))).where(
            AuditEvent.action == "auth.login", AuditEvent.occurred_at >= week_ago)) or 0
    failed_logins_15m = db.scalar(
        select(func.count()).select_from(AuditEvent).where(
            AuditEvent.action == "auth.login_failed", AuditEvent.occurred_at >= quarter_ago)) or 0

    task_status_rows = db.execute(select(Task.status, func.count()).group_by(Task.status)).all()
    tasks_by_status = {str(status): count for status, count in task_status_rows}
    tasks_total = sum(tasks_by_status.values())
    tasks_created_7d = db.scalar(
        select(func.count()).select_from(Task).where(Task.created_at >= week_ago)) or 0
    tasks_completed_7d = db.scalar(
        select(func.count()).select_from(Task).where(
            Task.status == "completed", Task.completed_at >= week_ago)) or 0
    tasks_overdue = db.scalar(
        select(func.count()).select_from(Task).where(
            Task.due_date < now.date(),
            Task.status.in_(("open", "in_progress", "blocked", "under_review")))) or 0

    outbox_pending = db.scalar(
        select(func.count()).select_from(OutboxEvent).where(
            OutboxEvent.status == OutboxStatus.pending)) or 0
    outbox_processing = db.scalar(
        select(func.count()).select_from(OutboxEvent).where(
            OutboxEvent.status == OutboxStatus.processing)) or 0
    outbox_failed = db.scalar(
        select(func.count()).select_from(OutboxEvent).where(
            OutboxEvent.status == OutboxStatus.permanent_failure)) or 0

    imports_total = db.scalar(select(func.count()).select_from(ImportJob)) or 0
    imports_committed = db.scalar(
        select(func.count()).select_from(ImportJob).where(ImportJob.status == "committed")) or 0

    audit_actions_24h = dict(db.execute(
        select(AuditEvent.action, func.count())
        .where(AuditEvent.occurred_at >= day_ago)
        .group_by(AuditEvent.action)).all())

    metrics = {
        "captured_at": now.isoformat(),
        "users": {"total": users_total, "active": users_active},
        "sessions_active": sessions_active,
        "logins": {"last_24h": logins_24h, "last_7d": logins_7d,
                   "distinct_users_7d": distinct_users_7d,
                   "failed_last_15m": failed_logins_15m},
        "tasks": {"total": tasks_total, "by_status": tasks_by_status,
                  "created_7d": tasks_created_7d, "completed_7d": tasks_completed_7d,
                  "overdue_active": tasks_overdue},
        "imports": {"total": imports_total, "committed": imports_committed},
        "outbox": {"pending": outbox_pending, "processing": outbox_processing,
                   "permanent_failure": outbox_failed},
        "audit_actions_24h": audit_actions_24h,
    }

    alerts: list[str] = []
    if failed_logins_15m >= LOGIN_FAILED_ALERT_THRESHOLD:
        alerts.append(f"SECURITY: {failed_logins_15m} failed logins in 15 minutes "
                      f"(threshold {LOGIN_FAILED_ALERT_THRESHOLD})")
    if outbox_failed > 0:
        alerts.append(f"DELIVERY: {outbox_failed} outbox event(s) in permanent_failure; "
                      "inspect outbox_events")
    if outbox_pending > 200:
        alerts.append(f"DELIVERY: outbox backlog {outbox_pending} pending events")
    if sessions_active > users_active * 50:
        alerts.append("ANOMALY: session count far exceeds active users")
    if tasks_overdue > 0:
        alerts.append(f"OPS: {tasks_overdue} active task(s) past due date")
    metrics["alerts"] = alerts
    return metrics


def check_health(base_url: str) -> dict:
    try:
        resp = httpx.get(f"{base_url}/api/v1/health", timeout=10.0)
        return {"ok": resp.status_code == 200 and resp.json().get("status") == "ok",
                "status_code": resp.status_code,
                "body": resp.json() if resp.status_code == 200 else resp.text[:200]}
    except Exception as exc:
        return {"ok": False, "status_code": 0, "body": str(exc)}


def save_snapshot(metrics: dict) -> Path:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    path = SNAPSHOT_DIR / f"snapshot-{stamp}.json"
    path.write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")
    old = sorted(SNAPSHOT_DIR.glob("snapshot-*.json"))
    for stale in old[:-KEEP_SNAPSHOTS]:
        stale.unlink(missing_ok=True)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="DecOps early-usage monitor")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--json", action="store_true", help="print JSON only")
    args = parser.parse_args()

    health = check_health(args.base_url)
    db = SessionLocal()
    try:
        metrics = gather(db)
    finally:
        db.close()
    metrics["health"] = health
    path = save_snapshot(metrics)

    if args.json:
        print(json.dumps(metrics, indent=2, default=str))
    else:
        print("== DecOps early-usage monitor ==")
        print(f"health: {'OK' if health['ok'] else 'DOWN'} ({args.base_url})  snapshot: {path}")
        t = metrics["tasks"]
        print(f"users: {metrics['users']['active']}/{metrics['users']['total']} active | "
              f"sessions: {metrics['sessions_active']} | logins 24h/7d: "
              f"{metrics['logins']['last_24h']}/{metrics['logins']['last_7d']} "
              f"({metrics['logins']['distinct_users_7d']} distinct users this week)")
        print(f"tasks: {t['total']} total | by status: {t['by_status']} | "
              f"created 7d: {t['created_7d']} | completed 7d: {t['completed_7d']} | "
              f"overdue: {t['overdue_active']}")
        print(f"imports: {metrics['imports']['committed']}/{metrics['imports']['total']} committed | "
              f"outbox: pending={metrics['outbox']['pending']} "
              f"processing={metrics['outbox']['processing']} "
              f"permanent_failure={metrics['outbox']['permanent_failure']}")
        top_actions = sorted(metrics["audit_actions_24h"].items(), key=lambda kv: -kv[1])[:8]
        print("audit 24h: " + ", ".join(f"{a}={c}" for a, c in top_actions))
        if metrics["alerts"]:
            print("ALERTS:")
            for alert in metrics["alerts"]:
                print(f"  !! {alert}")
        else:
            print("alerts: none")
    return 0 if health["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
