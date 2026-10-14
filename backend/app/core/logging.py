"""Structured JSON logging with request correlation support."""

import json
import logging
import sys
from datetime import UTC, datetime

from app.core.config import settings


class JsonFormatter(logging.Formatter):
    """Minimal JSON log formatter - one event per line, machine parseable."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Attached context (request_id, user_id, action, ...)
        extra = getattr(record, "context", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging() -> None:
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)

    # Route uvicorn loggers through the app's structured format
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True


def log_event(logger: logging.Logger, level: int, message: str, **context: object) -> None:
    """Log a message with structured context fields attached."""
    logger.log(level, message, extra={"context": context})
