"""Authentication service : login with throttling, session lifecycle,
and security event auditing."""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    generate_session_token,
    hash_session_token,
    new_session_expiry,
    verify_password,
)
from app.db.base import utcnow
from app.models import AccountStatus, User, UserSession
from app.services import audit_service

logger = logging.getLogger("decops.auth")


class LoginFailed(Exception):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def authenticate(db: Session, *, email: str, password: str) -> User:
    """Validate credentials. Raises LoginFailed with a safe, non-enumerating message."""
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    generic_failure = LoginFailed("Invalid email or password.", code="invalid_credentials")

    if user is None:
        # Constant-ish time: still run a hash comparison to reduce timing signals
        verify_password(password, "$argon2id$invalid-placeholder$value")
        raise generic_failure

    status_value = (
        user.account_status.value
        if isinstance(user.account_status, AccountStatus)
        else str(user.account_status)
    )
    if status_value != AccountStatus.active.value:
        audit_service.record_audit_event(
            db,
            action="auth.login_rejected",
            resource_type="user",
            resource_id=user.id,
            actor_user_id=user.id,
            reason="account_not_active",
            metadata={"account_status": status_value},
        )
        raise LoginFailed("This account is not active.", code="account_inactive")

    if user.is_locked():
        audit_service.record_audit_event(
            db,
            action="auth.login_rejected",
            resource_type="user",
            resource_id=user.id,
            actor_user_id=user.id,
            reason="account_locked",
        )
        raise LoginFailed(
            "Account temporarily locked due to failed login attempts. Try again later.",
            code="account_locked",
        )

    if not verify_password(password, user.authentication_reference or ""):
        user.failed_login_count += 1
        lock_reason = None
        if user.failed_login_count >= settings.max_failed_logins:
            user.locked_until = datetime.now(UTC) + timedelta(
                minutes=settings.login_lockout_minutes
            )
            user.failed_login_count = 0
            lock_reason = "max_failed_logins"
        audit_service.record_audit_event(
            db,
            action="auth.login_failed",
            resource_type="user",
            resource_id=user.id,
            actor_user_id=user.id,
            metadata={"failed_count": user.failed_login_count, "locked": lock_reason},
        )
        raise generic_failure

    return user


def create_session(
    db: Session,
    *,
    user: User,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[str, UserSession]:
    """Create a new server-side session; returns (raw_token, session)."""
    token = generate_session_token()
    session = UserSession(
        user_id=user.id,
        token_hash=hash_session_token(token),
        expires_at=new_session_expiry(settings.session_lifetime_minutes),
        ip_address=(ip_address or "")[:64] or None,
        user_agent=(user_agent or "")[:400] or None,
    )
    db.add(session)
    user.last_login_at = utcnow()
    user.failed_login_count = 0
    return token, session


def revoke_session(db: Session, session: UserSession) -> None:
    session.revoked_at = utcnow()


def resolve_session(db: Session, token: str | None) -> tuple[User, UserSession] | None:
    """Resolve a raw session token to (user, session) if it is valid and active.
    Returns None for missing/expired/revoked sessions or deactivated users -
    so revocation and deactivation take effect immediately."""
    if not token:
        return None
    session = db.scalar(
        select(UserSession).where(UserSession.token_hash == hash_session_token(token))
    )
    if session is None or not session.is_usable:
        return None
    user = session.user
    if user is None or not user.is_active:
        return None
    return user, session
