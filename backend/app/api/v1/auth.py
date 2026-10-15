"""Authentication endpoints (spec api: POST /auth/login, /auth/logout, GET /auth/me)."""

import logging

from fastapi import APIRouter, Request, Response, status

from app.api.deps import CurrentUser, DbSession, get_user_permission_codes
from app.core.config import Settings
from app.core.errors import AppError
from app.schemas.common import LoginRequest, MeResponse, RoleBrief
from app.services import audit_service, auth_service

logger = logging.getLogger("decops.api.auth")
router = APIRouter(prefix="/auth", tags=["Authentication"])


class InvalidCredentialsError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "invalid_credentials"
    message = "Invalid email or password."


class AccountStateError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "account_state"
    message = "Account cannot be used to sign in."


def _me_response(user, permission_codes: set[str]) -> MeResponse:
    return MeResponse(
        id=user.id,
        employee_code=user.employee_code,
        full_name=user.full_name,
        email=user.email,
        account_status=user.account_status,
        last_login_at=user.last_login_at,
        roles=[RoleBrief.model_validate(ur.role) for ur in user.roles],
        permissions=sorted(permission_codes),
    )


@router.post("/login", response_model=MeResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> MeResponse:
    settings: Settings = request.app.state.settings
    try:
        user = auth_service.authenticate(db, email=payload.email, password=payload.password)
    except auth_service.LoginFailed as exc:
        db.commit()  # persist throttling counters + security audit rows
        if exc.code == "invalid_credentials":
            raise InvalidCredentialsError() from exc
        raise AccountStateError(message=exc.message, details={"reason": exc.code}) from exc

    token, _session = auth_service.create_session(
        db,
        user=user,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    audit_service.record_audit_event(
        db,
        action="auth.login",
        resource_type="user",
        resource_id=user.id,
        actor=user,
    )
    db.commit()

    # HttpOnly session cookie (spec: server-managed sessions, not JS-readable)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_lifetime_minutes * 60,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )
    return _me_response(user, get_user_permission_codes(db, user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, user: CurrentUser, db: DbSession) -> None:
    settings: Settings = request.app.state.settings
    session = getattr(request.state, "user_session", None)
    if session is not None:
        auth_service.revoke_session(db, session)
        audit_service.record_audit_event(
            db,
            action="auth.logout",
            resource_type="user",
            resource_id=user.id,
            actor=user,
        )
        db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.get("/me", response_model=MeResponse)
def me(user: CurrentUser, db: DbSession) -> MeResponse:
    return _me_response(user, get_user_permission_codes(db, user))
