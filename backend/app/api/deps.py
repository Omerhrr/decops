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


def get_request_user(request: Request, db: DbSession) -> User:
    token = request.cookies.get(request.app.state.settings.session_cookie_name)
    resolved = auth_service.resolve_session(db, token)
    if resolved is None:
        raise AuthenticationError()
    user, session = resolved
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
