"""DecOps API application factory.

Modular monolith : route handlers stay thin,
business logic lives in services/domain, authorization is centralized.
"""

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import Settings, settings
from app.core.context import request_id_ctx
from app.core.errors import register_exception_handlers
from app.core.logging import log_event, setup_logging
from app.core.ratelimit import RateLimitMiddleware
from app.services import outbox_worker

logger = logging.getLogger("decops.app")


class RequestContextMiddleware:
    """Assigns a request id to every request for log/audit correlation."""

    def __init__(self, app) -> None:  # noqa: ANN001
        self.app = app

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        rid = uuid.uuid4().hex[:16]

        async def send_with_request_id(message) -> None:  # noqa: ANN001
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.append((b"x-request-id", rid.encode()))
            await send(message)

        token = request_id_ctx.set(rid)
        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            request_id_ctx.reset(token)


class SecurityHeadersMiddleware:
    """ hardening: baseline response headers on every API response.

    The API serves JSON only (the UI is the Nuxt origin), so a restrictive
    CSP plus no-sniff/no-frame/referrer defaults cost nothing and blunt
    content-sniffing, framing, and referrer leakage. Cache-control keeps
    authenticated task content out of shared caches. HSTS is added only for
    HTTPS deployments (secure_cookies=True) to avoid breaking plain HTTP
    sandbox access.
    """

    HEADERS: list[tuple[str, str]] = [
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"),
        ("Referrer-Policy", "no-referrer"),
        ("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"),
        ("Cache-Control", "no-store"),
    ]

    def __init__(self, app, *, hsts_seconds: int = 0) -> None:  # noqa: ANN001
        self.app = app
        self.hsts_seconds = hsts_seconds

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message) -> None:  # noqa: ANN001
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                existing = {k.lower() for k, _ in headers}
                for name, value in self.HEADERS:
                    if name.lower() not in existing:
                        headers.append((name.encode(), value.encode()))
                if self.hsts_seconds:
                    headers.append((b"strict-transport-security", f"max-age={self.hsts_seconds}".encode()))
            await send(message)

        await self.app(scope, receive, send_with_headers)


class RequestGuardMiddleware:
    """Defence-in-depth request guards.

    * Rejects bodies larger than ``max_request_bytes`` (Content-Length) before
      they are spooled to disk.
    * CSRF: for unsafe methods, a browser-supplied ``Origin`` must be in
      ``trusted_origins`` (when configured). SameSite=Lax cookies already block
      the classic attack; this closes same-site / subdomain gaps.
    """

    UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}

    def __init__(self, app, *, max_bytes: int, trusted_origins: list[str]) -> None:  # noqa: ANN001
        self.app = app
        self.max_bytes = max_bytes
        self.trusted = {o.rstrip("/").lower() for o in trusted_origins}

    async def _reject(self, send, status: int, code: str, message: str) -> None:  # noqa: ANN001
        import json

        body = json.dumps({"error": {"code": code, "message": message}}).encode()
        await send({"type": "http.response.start", "status": status, "headers": [
            (b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
        ]})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode().lower(): v.decode("latin-1") for k, v in scope["headers"]}
        length = headers.get("content-length")
        if length and length.isdigit() and int(length) > self.max_bytes:
            await self._reject(send, 413, "payload_too_large", "Request body is too large.")
            return
        if self.trusted and scope["method"] in self.UNSAFE:
            origin = headers.get("origin")
            if origin and origin.rstrip("/").lower() not in self.trusted:
                await self._reject(send, 403, "forbidden", "Cross-origin request blocked.")
                return
        await self.app(scope, receive, send)


def create_app(override_settings: Settings | None = None) -> FastAPI:
    app_settings = override_settings or settings
    if override_settings is None:
        app_settings.assert_production_ready()
    setup_logging()
    if app_settings.sentry_dsn:
        import sentry_sdk

        sentry_sdk.init(
            dsn=app_settings.sentry_dsn,
            environment=app_settings.environment,
            traces_sample_rate=app_settings.sentry_traces_sample_rate,
            send_default_pii=False,  # never ship emails/IPs/cookies to a third party
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Background transactional-outbox worker. Disabled in tests.
        worker_task = outbox_worker.start_worker()
        try:
            yield
        finally:
            await outbox_worker.stop_worker(worker_task)

    app = FastAPI(
        title=app_settings.app_name,
        version="1.0.0",
        description=(
            "DecOps Operations Management System API for Interdec - internal "
            "task and workflow management with RBAC, task-level access control, "
            "workflows, audit history, and spreadsheet migration."
        ),
        docs_url="/api/docs" if not app_settings.is_production else None,
        openapi_url="/api/openapi.json" if not app_settings.is_production else None,
        lifespan=lifespan,
    )
    app.state.settings = app_settings

    # Request id + structured access log
    app.add_middleware(RequestContextMiddleware)

    # Hardening: security headers on every response
    app.add_middleware(
        SecurityHeadersMiddleware,
        hsts_seconds=31536000 if app_settings.secure_cookies else 0,
    )

    app.add_middleware(
        RateLimitMiddleware,
        enabled=app_settings.rate_limit_enabled and app_settings.environment != "testing",
    )
    app.add_middleware(
        RequestGuardMiddleware,
        max_bytes=app_settings.max_request_bytes,
        trusted_origins=app_settings.trusted_origins,
    )

    # CORS fallback for direct API access (the Nuxt server normally proxies /api)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-Id"],
        expose_headers=["X-Request-Id"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=app_settings.api_v1_prefix)

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {"name": app_settings.app_name, "docs": "/api/docs"}

    @app.middleware("http")
    async def access_log(request: Request, call_next):  # noqa: ANN202
        try:
            response = await call_next(request)
        except Exception:
            log_event(
                logger, logging.ERROR, "request_failed",
                request_id=request_id_ctx.get(), path=request.url.path,
                method=request.method,
            )
            raise
        if request.url.path != "/api/v1/health":  # keep noise down
            log_event(
                logger, logging.INFO, "request",
                request_id=request_id_ctx.get(), path=request.url.path,
                method=request.method, status=response.status_code,
            )
        return response

    return app


app = create_app()
