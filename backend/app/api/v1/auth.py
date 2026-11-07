"""Authentication endpoints."""

import logging

import uuid
from datetime import datetime

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, EmailStr, Field

from app.api.deps import CurrentUser, DbSession, get_user_permission_codes
from app.core.config import Settings
from app.core.errors import AppError
from app.schemas.common import LoginRequest, MeResponse, RoleBrief
from app.services import account_service, audit_service, auth_service, settings_service

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


class MfaError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "mfa_required"
    message = "Verification code required."


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
        preferences=settings_service.get_user_preferences(user),
        mfa_enabled=bool(user.totp_enabled),
        must_change_password=bool(user.must_change_password),
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
        user = auth_service.authenticate(
            db, email=payload.email, password=payload.password, otp_code=payload.otp_code,
        )
    except auth_service.LoginFailed as exc:
        db.commit()  # persist throttling counters + security audit rows
        if exc.code == "invalid_credentials":
            raise InvalidCredentialsError() from exc
        if exc.code in {"mfa_required", "invalid_otp"}:
            raise MfaError(exc.message, code=exc.code) from exc
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

    # HttpOnly session cookie
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


# ----------------------------------------------------------------- password
class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=1, max_length=200)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=1, max_length=200)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(payload: ChangePasswordRequest, request: Request, user: CurrentUser, db: DbSession) -> None:
    account_service.change_password(
        db, user=user, current_session=getattr(request.state, "user_session", None),
        current_password=payload.current_password, new_password=payload.new_password,
    )
    db.commit()


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(payload: ForgotPasswordRequest, request: Request, db: DbSession) -> dict:
    account_service.request_password_reset(
        db, email=payload.email, ip=request.client.host if request.client else None,
    )
    db.commit()
    # Identical response whether or not the account exists.
    return {"message": "If that email belongs to an account, a reset link has been sent."}


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(payload: ResetPasswordRequest, db: DbSession) -> None:
    account_service.reset_password(db, token=payload.token, new_password=payload.new_password)
    db.commit()


# ---------------------------------------------------------------------- MFA
class MfaCodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=32)


class MfaDisableRequest(BaseModel):
    password: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=32)


@router.post("/mfa/setup")
def mfa_setup(user: CurrentUser, db: DbSession) -> dict:
    result = account_service.mfa_begin_setup(db, user=user)
    db.commit()
    return result


@router.post("/mfa/enable")
def mfa_enable(payload: MfaCodeRequest, user: CurrentUser, db: DbSession) -> dict:
    codes = account_service.mfa_enable(db, user=user, code=payload.code)
    db.commit()
    return {"recovery_codes": codes}


@router.post("/mfa/disable", status_code=status.HTTP_204_NO_CONTENT)
def mfa_disable(payload: MfaDisableRequest, user: CurrentUser, db: DbSession) -> None:
    account_service.mfa_disable(db, user=user, password=payload.password, code=payload.code)
    db.commit()


# ----------------------------------------------------------------- sessions
class SessionOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    expires_at: datetime
    ip_address: str | None = None
    user_agent: str | None = None
    current: bool = False


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(request: Request, user: CurrentUser, db: DbSession) -> list[SessionOut]:
    current = getattr(request.state, "user_session", None)
    return [
        SessionOut(
            id=s.id, created_at=s.created_at, expires_at=s.expires_at,
            ip_address=s.ip_address, user_agent=s.user_agent,
            current=bool(current and current.id == s.id),
        )
        for s in account_service.list_sessions(db, user=user)
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(session_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    if not account_service.revoke_session_by_id(db, user=user, session_id=session_id):
        from app.core.errors import NotFoundError

        raise NotFoundError("Session not found.")
    db.commit()


@router.post("/sessions/revoke-others", status_code=status.HTTP_204_NO_CONTENT)
def revoke_other_sessions(request: Request, user: CurrentUser, db: DbSession) -> None:
    current = getattr(request.state, "user_session", None)
    count = account_service.revoke_sessions(db, user.id, except_id=current.id if current else None)
    audit_service.record_audit_event(
        db, action="session.revoked_others", resource_type="user", resource_id=user.id, actor=user,
        metadata={"count": count},
    )
    db.commit()
