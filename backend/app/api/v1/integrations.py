"""Integrations: personal API tokens, outgoing webhooks, recurring tasks."""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, get_user_permission_codes, require_permission
from app.core.context import current_request_id
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.core.security import encrypt_secret, generate_url_token, hash_token
from app.domain.notifications import EventType
from app.models import ApiToken, Department, RecurringTask, User, Webhook
from app.services import audit_service, recurrence_service, webhook_service
from app.api.deps import TOKEN_PREFIX

router = APIRouter(prefix="/integrations", tags=["Integrations"])
MAX_TOKENS = 10
MAX_WEBHOOKS = 10
MAX_RECURRING = 50


def _auth(request: Request, user: CurrentUser) -> User:
    request.state.user = user
    return user


# ------------------------------------------------------------------ API tokens

class TokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    scope: Literal["read", "write"] = "read"
    expires_in_days: int | None = Field(default=90, ge=1, le=365)


def _token_out(t: ApiToken) -> dict:
    return {
        "id": str(t.id), "name": t.name, "prefix": t.prefix, "scope": t.scope,
        "expires_at": t.expires_at.isoformat() if t.expires_at else None,
        "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None,
        "revoked": t.revoked_at is not None,
    }


@router.get("/api-tokens")
def list_tokens(db: DbSession, user: User = Depends(_auth)) -> list[dict]:
    rows = db.scalars(select(ApiToken).where(ApiToken.user_id == user.id, ApiToken.revoked_at.is_(None))
                      .order_by(ApiToken.created_at.desc())).all()
    return [_token_out(r) for r in rows]


@router.post("/api-tokens", status_code=201)
def create_token(payload: TokenCreate, db: DbSession, user: User = Depends(_auth)) -> dict:
    active = db.scalar(select(func.count(ApiToken.id)).where(
        ApiToken.user_id == user.id, ApiToken.revoked_at.is_(None))) or 0
    if active >= MAX_TOKENS:
        raise ConflictError(f"You can have up to {MAX_TOKENS} active tokens.", code="token_limit")
    raw = TOKEN_PREFIX + generate_url_token()
    row = ApiToken(
        user_id=user.id, name=payload.name.strip(), token_hash=hash_token(raw), prefix=raw[:8],
        scope=payload.scope,
        expires_at=datetime.now(UTC) + timedelta(days=payload.expires_in_days) if payload.expires_in_days else None,
    )
    db.add(row)
    db.flush()
    audit_service.record_audit_event(
        db, action="session.api_token_created", resource_type="api_token", resource_id=row.id, actor=user,
        request_id=current_request_id(), change_summary=f"API token '{row.name}' created ({row.scope})")
    db.commit()
    return {**_token_out(row), "token": raw}  # the only time the secret is shown


@router.delete("/api-tokens/{token_id}", status_code=204)
def revoke_token(token_id: uuid.UUID, db: DbSession, user: User = Depends(_auth)) -> None:
    row = db.get(ApiToken, token_id)
    if row is None or row.user_id != user.id:
        raise NotFoundError("Token not found.")
    row.revoked_at = datetime.now(UTC)
    audit_service.record_audit_event(
        db, action="session.api_token_revoked", resource_type="api_token", resource_id=row.id, actor=user,
        request_id=current_request_id(), change_summary=f"API token '{row.name}' revoked")
    db.commit()


# -------------------------------------------------------------------- webhooks

_admin = Depends(require_permission("settings.manage"))


class WebhookCreate(BaseModel):
    url: str = Field(min_length=8, max_length=500)
    events: list[str] = Field(default_factory=list)


def _hook_out(h: Webhook) -> dict:
    return {
        "id": str(h.id), "url": h.url, "events": h.events or [], "active": h.active,
        "last_status": h.last_status,
        "last_delivery_at": h.last_delivery_at.isoformat() if h.last_delivery_at else None,
    }


@router.get("/webhooks", dependencies=[_admin])
def list_webhooks(db: DbSession) -> list[dict]:
    return [_hook_out(h) for h in db.scalars(select(Webhook).order_by(Webhook.created_at)).all()]


@router.post("/webhooks", status_code=201, dependencies=[_admin])
def create_webhook(payload: WebhookCreate, request: Request, db: DbSession) -> dict:
    actor: User = request.state.user
    unknown = [e for e in payload.events if e not in EventType.ALL]
    if unknown:
        raise ValidationFailedError(f"Unknown event type: {unknown[0]}")
    if (db.scalar(select(func.count(Webhook.id))) or 0) >= MAX_WEBHOOKS:
        raise ConflictError(f"Up to {MAX_WEBHOOKS} webhooks are supported.", code="webhook_limit")
    webhook_service.validate_target_url(payload.url)
    secret = "whsec_" + generate_url_token()
    hook = Webhook(url=payload.url, secret_enc=encrypt_secret(secret), events=payload.events,
                   active=True, created_by_id=actor.id, consecutive_failures=0)
    db.add(hook)
    db.flush()
    audit_service.record_audit_event(
        db, action="settings.webhook_created", resource_type="webhook", resource_id=hook.id, actor=actor,
        request_id=current_request_id(), change_summary=f"Webhook created for {payload.url}")
    db.commit()
    return {**_hook_out(hook), "secret": secret}  # shown once


@router.post("/webhooks/{hook_id}/toggle", dependencies=[_admin])
def toggle_webhook(hook_id: uuid.UUID, db: DbSession) -> dict:
    hook = db.get(Webhook, hook_id)
    if hook is None:
        raise NotFoundError("Webhook not found.")
    hook.active = not hook.active
    if hook.active:
        hook.consecutive_failures = 0
    db.commit()
    return _hook_out(hook)


@router.delete("/webhooks/{hook_id}", status_code=204, dependencies=[_admin])
def delete_webhook(hook_id: uuid.UUID, request: Request, db: DbSession) -> None:
    hook = db.get(Webhook, hook_id)
    if hook is None:
        raise NotFoundError("Webhook not found.")
    audit_service.record_audit_event(
        db, action="settings.webhook_deleted", resource_type="webhook", resource_id=hook.id,
        actor=request.state.user, request_id=current_request_id(), change_summary="Webhook deleted")
    db.delete(hook)
    db.commit()


# ------------------------------------------------------------- recurring tasks

_creator = Depends(require_permission("tasks.create"))


class RecurringIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    accountable_pm_id: uuid.UUID
    visibility_mode: Literal["participants", "private", "department_scoped", "custom"] = "participants"
    department_ids: list[uuid.UUID] = Field(default_factory=list)
    frequency: Literal["daily", "weekly", "monthly"]
    interval: int = Field(default=1, ge=1, le=12)
    due_after_days: int = Field(default=7, ge=0, le=365)
    first_run_on: date | None = None


def _rec_out(r: RecurringTask) -> dict:
    return {
        "id": str(r.id), "title": r.title, "priority": r.priority, "frequency": r.frequency,
        "interval": r.interval, "due_after_days": r.due_after_days, "next_run_on": r.next_run_on.isoformat(),
        "active": r.active, "last_error": r.last_error, "accountable_pm_id": str(r.accountable_pm_id),
        "visibility_mode": r.visibility_mode,
        "last_run_at": r.last_run_at.isoformat() if r.last_run_at else None,
    }


def _can_manage_all(db, user: User) -> bool:
    return "tasks.manage_all" in get_user_permission_codes(db, user)


@router.get("/recurring", dependencies=[_creator])
def list_recurring(request: Request, db: DbSession) -> list[dict]:
    user: User = request.state.user
    stmt = select(RecurringTask).order_by(RecurringTask.next_run_on)
    if not _can_manage_all(db, user):
        stmt = stmt.where(RecurringTask.created_by_id == user.id)
    return [_rec_out(r) for r in db.scalars(stmt).all()]


@router.post("/recurring", status_code=201, dependencies=[_creator])
def create_recurring(payload: RecurringIn, request: Request, db: DbSession) -> dict:
    user: User = request.state.user
    if db.get(User, payload.accountable_pm_id) is None:
        raise ValidationFailedError("The selected accountable PM does not exist.")
    for dep_id in payload.department_ids:
        if db.get(Department, dep_id) is None:
            raise ValidationFailedError("A selected department does not exist.")
    if payload.visibility_mode == "department_scoped" and not payload.department_ids:
        raise ValidationFailedError("Department-scoped tasks need at least one department.")
    owned = db.scalar(select(func.count(RecurringTask.id)).where(RecurringTask.created_by_id == user.id)) or 0
    if owned >= MAX_RECURRING:
        raise ConflictError(f"Up to {MAX_RECURRING} recurring tasks per person.", code="recurring_limit")
    first = payload.first_run_on or datetime.now(UTC).date()
    row = RecurringTask(
        created_by_id=user.id, title=payload.title.strip(), description=payload.description,
        priority=payload.priority, accountable_pm_id=payload.accountable_pm_id,
        visibility_mode=payload.visibility_mode, department_ids=[str(d) for d in payload.department_ids],
        frequency=payload.frequency, interval=payload.interval, due_after_days=payload.due_after_days,
        next_run_on=first, active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _rec_out(row)


def _owned_or_404(db, user: User, rec_id: uuid.UUID) -> RecurringTask:
    row = db.get(RecurringTask, rec_id)
    if row is None or (row.created_by_id != user.id and not _can_manage_all(db, user)):
        raise NotFoundError("Recurring task not found.")
    return row


@router.post("/recurring/{rec_id}/toggle", dependencies=[_creator])
def toggle_recurring(rec_id: uuid.UUID, request: Request, db: DbSession) -> dict:
    row = _owned_or_404(db, request.state.user, rec_id)
    row.active = not row.active
    db.commit()
    return _rec_out(row)


@router.delete("/recurring/{rec_id}", status_code=204, dependencies=[_creator])
def delete_recurring(rec_id: uuid.UUID, request: Request, db: DbSession) -> None:
    db.delete(_owned_or_404(db, request.state.user, rec_id))
    db.commit()
