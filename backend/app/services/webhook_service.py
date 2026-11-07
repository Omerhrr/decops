"""Outgoing webhooks: SSRF-guarded, HMAC-signed, best-effort delivery.

Payloads contain identifiers only (event type, task id/number, actor id,
time) - never titles, descriptions or comment text - so a webhook subscriber
cannot receive content a confidential task would otherwise protect.
"""

import hashlib
import hmac
import ipaddress
import json
import logging
import socket
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ValidationFailedError
from app.core.security import decrypt_secret
from app.models import OutboxEvent, Task, Webhook

logger = logging.getLogger("decops.webhooks")
MAX_FAILURES_BEFORE_DISABLE = 10


def validate_target_url(url: str) -> None:
    """Reject non-https (outside dev) and any host resolving to a non-public address."""
    cfg = get_settings()
    parsed = urlparse(url)
    allowed = {"https"} if cfg.environment == "production" else {"https", "http"}
    if parsed.scheme not in allowed or not parsed.hostname or parsed.username or parsed.password:
        raise ValidationFailedError("Webhook URL must be an https URL without credentials.")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValidationFailedError("Webhook host could not be resolved.") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ValidationFailedError("Webhook URL must point to a public address.")


def sign(secret: str, timestamp: str, body: bytes) -> str:
    mac = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


def _deliver(hook: Webhook, event_type: str, body: bytes) -> str:
    validate_target_url(hook.url)  # re-check at send time
    ts = str(int(datetime.now(UTC).timestamp()))
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "DecOps-Webhook/1",
        "X-DecOps-Event": event_type,
        "X-DecOps-Timestamp": ts,
        "X-DecOps-Signature": sign(decrypt_secret(hook.secret_enc), ts, body),
    }
    resp = httpx.post(hook.url, content=body, headers=headers, timeout=5.0, follow_redirects=False)
    return f"HTTP {resp.status_code}"


def dispatch(db: Session, event: OutboxEvent, task: Task) -> None:
    """Send an event to every matching active webhook. Never raises."""
    try:
        hooks = db.scalars(select(Webhook).where(Webhook.active.is_(True))).all()
        if not hooks:
            return
        body = json.dumps({
            "event": event.event_type,
            "task_id": str(task.id),
            "task_number": task.task_number,
            "actor_id": event.payload.get("actor_id"),
            "occurred_at": datetime.now(UTC).isoformat(),
        }).encode()
        for hook in hooks:
            if hook.events and event.event_type not in hook.events:
                continue
            try:
                status = _deliver(hook, event.event_type, body)
                ok = status.startswith("HTTP 2")
            except Exception as exc:  # noqa: BLE001 - one bad hook must not affect others
                status, ok = f"error: {str(exc)[:150]}", False
            hook.last_status = status[:200]
            hook.last_delivery_at = datetime.now(UTC)
            hook.consecutive_failures = 0 if ok else (hook.consecutive_failures or 0) + 1
            if hook.consecutive_failures >= MAX_FAILURES_BEFORE_DISABLE:
                hook.active = False
                logger.warning("webhook_disabled", extra={"context": {"webhook": str(hook.id)}})
    except Exception:  # pragma: no cover - defensive
        logger.exception("webhook_dispatch_failed")
