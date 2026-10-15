"""Request-scoped context (correlation ids shared between middleware and handlers)."""

from contextvars import ContextVar

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def current_request_id() -> str:
    return request_id_ctx.get()
