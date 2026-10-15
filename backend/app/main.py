"""DecOps API application factory.

Modular monolith (spec backend_architecture): route handlers stay thin,
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


def create_app(override_settings: Settings | None = None) -> FastAPI:
    app_settings = override_settings or settings
    setup_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Background transactional-outbox worker (Phase 6). Disabled in tests.
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
