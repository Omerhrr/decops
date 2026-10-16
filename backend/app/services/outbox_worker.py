"""Background outbox worker (deliverable: "Background worker" +
"Delivery retry handling").

Runs as an asyncio task inside the FastAPI lifespan. Each tick uses its own
database session, processes due outbox events (one commit per event), and
sweeps deadlines. All errors are contained: a bad tick logs and retries on
the next interval, it never crashes the loop.
"""

import asyncio
import logging
from datetime import UTC, datetime

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services import notification_service

logger = logging.getLogger("decops.worker")


async def outbox_worker_loop() -> None:
    cfg = get_settings()
    interval = max(cfg.outbox_worker_interval_seconds, 5.0)
    logger.info("outbox_worker_started", extra={"context": {"interval_seconds": interval}})
    while True:
        try:
            await asyncio.to_thread(_run_pass)
        except asyncio.CancelledError:  # shutdown
            logger.info("outbox_worker_stopped")
            raise
        except Exception:
            logger.exception("outbox_worker_pass_failed")
        await asyncio.sleep(interval)


def _run_pass() -> dict:
    db = SessionLocal()
    try:
        counts = notification_service.worker_pass(db, now=datetime.now(UTC))
        if counts.get("claimed") or counts.get("deadline_created"):
            logger.info("worker_pass", extra={"context": counts})
        return counts
    finally:
        db.close()


def start_worker() -> asyncio.Task | None:
    """Start the loop unless disabled (tests / explicit opt-out)."""
    cfg = get_settings()
    if not cfg.outbox_worker_enabled or cfg.environment == "testing":
        return None
    return asyncio.create_task(outbox_worker_loop())


async def stop_worker(task: asyncio.Task | None) -> None:
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
