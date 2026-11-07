"""Shared API dependencies: authentication and permission resolution.

Authorization pipeline:
1. Authenticate via session cookie
2. Confirm account + session are active
3. (Per-route) check required global permission
Task-level authorization lands with the task resources.
"""

import uuid
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.errors import AuthenticationError
from app.db.session import get_db
from app.models import User
from app.services import auth_service

DbSession = Annotated[Session, Depends(get_db)]

# Paths a user with must_change_password may still call.
_PASSWORD_CHANGE_EXEMPT = {
    "/api/v1/auth/me", "/api/v1/auth/logout", "/api/v1/auth/change-password",
}


TOKEN_PREFIX = "dcp_"


def _user_from_api_token(request: Request, db: Session, raw: str) -> User:
    """Authenticate a personal API token. The token acts as its owner (never
    with extra rights); read-scoped tokens may only use safe methods."""
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.core.errors import PermissionDeniedError
    from app.core.security import hash_token
    from app.models import AccountStatus, ApiToken

    row = db.scalar(select(ApiToken).where(ApiToken.token_hash == hash_token(raw)))
    now = datetime.now(UTC)
    if row is None or row.revoked_at is not None or (row.expires_at is not None and row.expires_at <= now):
        raise AuthenticationError()
    user = db.get(User, row.user_id)
    if user is None or user.account_status != AccountStatus.active:
        raise AuthenticationError()
    path = request.url.path
    if (path.startswith("/api/v1/auth/") and path != "/api/v1/auth/me") or path.startswith("/api/v1/integrations/api-tokens"):
        raise PermissionDeniedError()  # account security + token management need a real session
    if row.scope != "write" and request.method not in ("GET", "HEAD", "OPTIONS"):
        raise PermissionDeniedError()
    row.last_used_at = now
    db.commit()
    request.state.via_api_token = True
    return user


def get_request_user(request: Request, db: DbSession) -> User:
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        raw = auth_header[7:].strip()
        if raw.startswith(TOKEN_PREFIX):
            user = _user_from_api_token(request, db, raw)
            if user.must_change_password:
                from app.core.errors import PasswordChangeRequiredError

                raise PasswordChangeRequiredError()
            request.state.user_session = None
            return user
    token = request.cookies.get(request.app.state.settings.session_cookie_name)
    resolved = auth_service.resolve_session(db, token)
    if resolved is None:
        raise AuthenticationError()
    user, session = resolved
    if user.must_change_password and request.url.path not in _PASSWORD_CHANGE_EXEMPT:
        from app.core.errors import PasswordChangeRequiredError

        raise PasswordChangeRequiredError()
    # Attach the session row for handlers that need it (e.g., logout revocation)
    request.state.user_session = session
    return user


CurrentUser = Annotated[User, Depends(get_request_user)]


def get_user_permission_codes(db: Session, user: User) -> set[str]:
    """Collect distinct permission codes from the user's global roles.
    Scoped roles (department/task) are evaluated by task-level authz."""
    codes: set[str] = set()
    for user_role in user.roles:
        if user_role.scope_type != "global":
            continue
        for link in user_role.role.permissions:
            codes.add(link.permission.code)
    return codes


def require_permission(*permission_codes: str):
    """Dependency factory: allow only users holding ANY of the given permissions."""

    def checker(request: Request, user: CurrentUser, db: DbSession) -> User:
        codes = get_user_permission_codes(db, user)
        request.state.permission_codes = codes
        request.state.user = user  # handlers may need the actor for audit trails
        if not codes & set(permission_codes):
            # 404, not 403: do not confirm the existence of protected resources
            from app.core.errors import PermissionDeniedError

            raise PermissionDeniedError()
        return user

    return checker


def parse_uuid(value: str) -> uuid.UUID:
    import uuid as _uuid

    try:
        return _uuid.UUID(value)
    except ValueError as exc:
        from app.core.errors import ValidationFailedError

        raise ValidationFailedError("Invalid identifier format.") from exc
