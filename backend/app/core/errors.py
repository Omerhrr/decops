"""Consistent error responses.

Every error returned by the API has the shape:
    {"error": {"code": "<MACHINE_CODE>", "message": "<human readable>", "details": ...}}
so the frontend has a single, predictable contract. Access-denied responses for
missing resources use 404 (not 403) to avoid leaking the existence of
restricted resources (spec: "Avoid leaking restricted resource existence").
"""

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.workflow import WorkflowTransitionError

logger = logging.getLogger("decops.errors")


class AppError(Exception):
    """Base class for expected application errors."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"
    message: str = "Invalid request."

    def __init__(
        self, message: str | None = None, *, details: Any = None, code: str | None = None
    ) -> None:
        if code is not None:
            self.code = code
        self.message = message or self.message
        self.details = details
        super().__init__(self.message)


class AuthenticationError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthenticated"
    message = "Authentication required."


class PermissionDeniedError(AppError):
    """Returned as 404 to avoid confirming the existence of restricted resources."""

    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    message = "Resource not found."


class NotFoundError(AppError):
    """The resource genuinely does not exist (distinct from permission denial)."""

    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    message = "Resource not found."


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    message = "The request conflicts with the current state."


class ValidationFailedError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "validation_failed"
    message = "Validation failed."


def _error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        err["details"] = details
    return {"error": err}


def _clean_validation_errors(errors: list) -> list:
    """Pydantic 2.14+ embeds raw exception objects in `ctx.error`, which are
    not JSON serializable — stringify them and encode the rest safely."""
    from fastapi.encoders import jsonable_encoder

    clean: list = []
    for err in errors:
        item = dict(err)
        ctx = item.get("ctx")
        if isinstance(ctx, dict):
            item["ctx"] = {
                k: (str(v) if isinstance(v, Exception) else v) for k, v in ctx.items()
            }
        try:
            clean.append(jsonable_encoder(item))
        except Exception:  # noqa: BLE001 - never fail the error path itself
            clean.append({"type": item.get("type"), "loc": item.get("loc"),
                          "msg": item.get("msg")})
    return clean


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(WorkflowTransitionError)
    async def workflow_rule_handler(_: Request, exc: WorkflowTransitionError) -> JSONResponse:
        # Invalid transitions, cycles, gates -> 409; missing justification or
        # unknown status -> 422 (consistent with the task lifecycle mapping).
        status_code = (
            422 if exc.code in {"reason_required", "invalid_status", "self_dependency"}
            else 409
        )
        return JSONResponse(status_code=status_code, content=_error_body(exc.code, str(exc)))

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_body(
                "validation_failed",
                "Request validation failed.",
                details={"errors": _clean_validation_errors(exc.errors())},
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code_map = {
            401: "unauthenticated",
            403: "forbidden",
            404: "not_found",
            409: "conflict",
            429: "rate_limited",
        }
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(code_map.get(exc.status_code, "http_error"), str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled exception",
            extra={"context": {"path": request.url.path, "method": request.method}},
        )
        return JSONResponse(
            status_code=500,
            content=_error_body("internal_error", "An internal error occurred."),
        )
