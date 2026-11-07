"""Audit log viewer: filterable, paginated, CSV-exportable.

* ``audit.read`` (Read-Only Auditor): every event.
* ``audit.security.read`` (System Administrator): security events only
  (sign-in, password, two-factor, session, user and role changes) - business
  content stays out of reach of technical administration.
"""

import csv
import io
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, require_permission
from app.models import AuditEvent, User

router = APIRouter(prefix="/audit", tags=["Audit"])

SECURITY_PREFIXES = ("auth.", "password.", "mfa.", "session.", "user.", "role.", "settings.")


def _filters(request: Request, *, q, action, resource_type, actor_id, since, until):
    codes: set[str] = request.state.permission_codes
    conds = []
    if "audit.read" not in codes:
        conds.append(or_(*[AuditEvent.action.like(f"{p}%") for p in SECURITY_PREFIXES]))
    if action:
        conds.append(AuditEvent.action.like(f"{action}%"))
    if resource_type:
        conds.append(AuditEvent.resource_type == resource_type)
    if actor_id:
        conds.append(AuditEvent.actor_user_id == actor_id)
    if since:
        conds.append(AuditEvent.occurred_at >= since)
    if until:
        conds.append(AuditEvent.occurred_at <= until)
    if q:
        like = f"%{q.strip()}%"
        conds.append(or_(AuditEvent.change_summary.ilike(like), AuditEvent.action.ilike(like),
                         AuditEvent.resource_id.ilike(like)))
    return conds


def _rows(db: Session, conds, limit: int, offset: int):
    stmt = (
        select(AuditEvent, User.full_name, User.email)
        .join(User, User.id == AuditEvent.actor_user_id, isouter=True)
        .where(and_(*conds)) if conds else
        select(AuditEvent, User.full_name, User.email).join(User, User.id == AuditEvent.actor_user_id, isouter=True)
    )
    return db.execute(stmt.order_by(AuditEvent.occurred_at.desc()).limit(limit).offset(offset)).all()


def _out(e: AuditEvent, name: str | None, email: str | None) -> dict:
    return {
        "id": str(e.id), "occurred_at": e.occurred_at.isoformat(), "action": e.action,
        "resource_type": e.resource_type, "resource_id": e.resource_id,
        "actor_id": str(e.actor_user_id) if e.actor_user_id else None,
        "actor_name": name, "actor_email": email,
        "change_summary": e.change_summary, "reason": e.reason,
        "request_id": e.request_id, "metadata": e.metadata_json or {},
    }


@router.get("/events", dependencies=[Depends(require_permission("audit.read", "audit.security.read"))])
def list_events(
    request: Request, db: DbSession,
    q: str | None = Query(None, max_length=200),
    action: str | None = Query(None, max_length=100),
    resource_type: str | None = Query(None, max_length=100),
    actor_id: uuid.UUID | None = None,
    since: datetime | None = None, until: datetime | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
) -> dict:
    conds = _filters(request, q=q, action=action, resource_type=resource_type,
                     actor_id=actor_id, since=since, until=until)
    total_stmt = select(func.count(AuditEvent.id))
    if conds:
        total_stmt = total_stmt.where(and_(*conds))
    total = db.scalar(total_stmt) or 0
    rows = _rows(db, conds, page_size, (page - 1) * page_size)
    return {"items": [_out(*r) for r in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/events/export", dependencies=[Depends(require_permission("audit.read", "audit.security.read"))])
def export_events(
    request: Request, db: DbSession,
    q: str | None = Query(None, max_length=200), action: str | None = Query(None, max_length=100),
    resource_type: str | None = Query(None, max_length=100), actor_id: uuid.UUID | None = None,
    since: datetime | None = None, until: datetime | None = None,
) -> Response:
    conds = _filters(request, q=q, action=action, resource_type=resource_type,
                     actor_id=actor_id, since=since, until=until)
    rows = _rows(db, conds, 10_000, 0)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["occurred_at", "action", "actor", "resource_type", "resource_id", "summary", "reason", "request_id"])

    def safe(v):  # neutralise spreadsheet formula injection
        v = "" if v is None else str(v)
        return "'" + v if v[:1] in ("=", "+", "-", "@") else v

    for e, name, email in rows:
        w.writerow([e.occurred_at.isoformat(), e.action, safe(email or name), e.resource_type,
                    e.resource_id, safe(e.change_summary), safe(e.reason), e.request_id])
    return Response(
        content=buf.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="audit_events.csv"'},
    )
