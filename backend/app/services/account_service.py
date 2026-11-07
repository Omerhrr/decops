"""Account security: password change/reset, TOTP two-factor, session management.

Every operation writes an audit event. Secrets (passwords, reset tokens, TOTP
secrets, recovery codes) never enter audit metadata or logs.
"""

import io
import logging
import uuid
from datetime import UTC, datetime, timedelta

import segno
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import settings
from app.core.errors import AppError, ValidationFailedError
from app.db.base import utcnow
from app.models import PasswordResetToken, User, UserSession
from app.services import audit_service, email_sender

logger = logging.getLogger("decops.account")


class AccountError(AppError):
    code = "account_error"


def _check_policy(password: str, user: User) -> None:
    problem = security.password_policy_problem(password, email=user.email)
    if problem:
        raise ValidationFailedError(problem, code="weak_password")


def revoke_sessions(db: Session, user_id: uuid.UUID, *, except_id: uuid.UUID | None = None) -> int:
    stmt = (
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    if except_id is not None:
        stmt = stmt.where(UserSession.id != except_id)
    return db.execute(stmt).rowcount or 0


# ---------------------------------------------------------------- password
def change_password(
    db: Session, *, user: User, current_session: UserSession | None,
    current_password: str, new_password: str,
) -> None:
    if not security.verify_password(current_password, user.authentication_reference or ""):
        audit_service.record_audit_event(
            db, action="password.change_failed", resource_type="user", resource_id=user.id, actor=user,
        )
        db.commit()  # persist the audit row even though we reject
        raise AccountError("Current password is incorrect.", code="invalid_current_password")
    if security.verify_password(new_password, user.authentication_reference or ""):
        raise ValidationFailedError("Choose a password you have not used before.", code="password_reused")
    _check_policy(new_password, user)
    user.authentication_reference = security.hash_password(new_password)
    user.must_change_password = False
    user.password_changed_at = utcnow()
    revoked = revoke_sessions(db, user.id, except_id=current_session.id if current_session else None)
    audit_service.record_audit_event(
        db, action="password.changed", resource_type="user", resource_id=user.id, actor=user,
        metadata={"other_sessions_revoked": revoked},
    )


def request_password_reset(db: Session, *, email: str, ip: str | None) -> None:
    """Always silent about whether the account exists (no enumeration)."""
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or not user.is_active:
        return
    # invalidate older outstanding tokens
    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=utcnow())
    )
    token = security.generate_url_token()
    db.add(PasswordResetToken(
        user_id=user.id, token_hash=security.hash_token(token),
        expires_at=datetime.now(UTC) + timedelta(minutes=settings.password_reset_minutes),
    ))
    audit_service.record_audit_event(
        db, action="password.reset_requested", resource_type="user", resource_id=user.id,
        actor_user_id=user.id, metadata={"ip": ip},
    )
    link = f"{settings.public_base_url.rstrip('/')}/reset-password?token={token}"
    body = (
        f"Hello {user.full_name},\n\n"
        "Someone asked to reset your DecOps password. If it was you, open this link "
        f"within {settings.password_reset_minutes} minutes:\n\n{link}\n\n"
        "If you did not ask for this, ignore this email; your password is unchanged."
    )
    try:
        email_sender.send_email(to_email=user.email, subject="Reset your DecOps password", body=body)
    except email_sender.EmailError:
        logger.exception("password_reset_email_failed")
    if not settings.email_notifications_enabled and not settings.is_production:
        # Dev convenience only: never log live reset links in production.
        logger.warning("DEV reset link for %s: %s", user.email, link)


def reset_password(db: Session, *, token: str, new_password: str) -> User:
    row = db.scalar(select(PasswordResetToken).where(
        PasswordResetToken.token_hash == security.hash_token(token or "")
    ))
    now = utcnow()
    if row is None or row.used_at is not None or row.expires_at <= now:
        raise AccountError("This reset link is invalid or has expired.", code="invalid_reset_token")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise AccountError("This reset link is invalid or has expired.", code="invalid_reset_token")
    _check_policy(new_password, user)
    user.authentication_reference = security.hash_password(new_password)
    user.must_change_password = False
    user.password_changed_at = now
    user.failed_login_count = 0
    user.locked_until = None
    row.used_at = now
    revoke_sessions(db, user.id)
    audit_service.record_audit_event(
        db, action="password.reset_completed", resource_type="user", resource_id=user.id, actor_user_id=user.id,
    )
    return user


# --------------------------------------------------------------------- MFA
def _qr_data_uri(uri: str) -> str:
    buf = io.BytesIO()
    segno.make(uri, error="m").save(buf, kind="svg", scale=5, border=2, dark="#0f172a")
    import base64

    return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()


def mfa_begin_setup(db: Session, *, user: User) -> dict:
    if user.totp_enabled:
        raise AccountError("Two-factor authentication is already enabled.", code="mfa_already_enabled")
    secret = security.new_totp_secret()
    user.totp_secret_enc = security.encrypt_secret(secret)  # pending until confirmed
    uri = security.totp_uri(secret, user.email)
    return {"secret": secret, "otpauth_uri": uri, "qr_svg_data_uri": _qr_data_uri(uri)}


def mfa_enable(db: Session, *, user: User, code: str) -> list[str]:
    if user.totp_enabled or not user.totp_secret_enc:
        raise AccountError("Start two-factor setup first.", code="mfa_setup_required")
    if not security.verify_totp(security.decrypt_secret(user.totp_secret_enc), code):
        raise AccountError("That code is not valid. Check your authenticator app and try again.", code="invalid_otp")
    codes = security.generate_recovery_codes()
    user.totp_enabled = True
    user.recovery_code_hashes = [security.hash_recovery_code(c) for c in codes]
    audit_service.record_audit_event(db, action="mfa.enabled", resource_type="user", resource_id=user.id, actor=user)
    return codes


def mfa_disable(db: Session, *, user: User, password: str, code: str) -> None:
    if not security.verify_password(password, user.authentication_reference or ""):
        raise AccountError("Password is incorrect.", code="invalid_current_password")
    if not verify_second_factor(db, user, code):
        raise AccountError("That code is not valid.", code="invalid_otp")
    clear_mfa(user)
    audit_service.record_audit_event(db, action="mfa.disabled", resource_type="user", resource_id=user.id, actor=user)


def clear_mfa(user: User) -> None:
    user.totp_enabled = False
    user.totp_secret_enc = None
    user.recovery_code_hashes = None


def admin_reset_mfa(db: Session, *, actor: User, user: User) -> None:
    clear_mfa(user)
    revoke_sessions(db, user.id)
    audit_service.record_audit_event(
        db, action="mfa.admin_reset", resource_type="user", resource_id=user.id, actor=actor,
        change_summary=f"Two-factor reset for {user.email}",
    )


def verify_second_factor(db: Session, user: User, code: str) -> bool:
    """Accept a current TOTP code or (consuming it) an unused recovery code."""
    if not user.totp_enabled or not user.totp_secret_enc:
        return False
    if security.verify_totp(security.decrypt_secret(user.totp_secret_enc), code):
        return True
    hashed = security.hash_recovery_code(code or "")
    codes = list(user.recovery_code_hashes or [])
    if hashed in codes:
        codes.remove(hashed)
        user.recovery_code_hashes = codes  # reassign so the JSON change is persisted
        audit_service.record_audit_event(
            db, action="mfa.recovery_code_used", resource_type="user", resource_id=user.id,
            actor_user_id=user.id, metadata={"remaining": len(codes)},
        )
        return True
    return False


# ---------------------------------------------------------------- sessions
def list_sessions(db: Session, *, user: User) -> list[UserSession]:
    now = utcnow()
    return list(db.scalars(
        select(UserSession)
        .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None), UserSession.expires_at > now)
        .order_by(UserSession.created_at.desc())
    ).all())


def revoke_session_by_id(db: Session, *, user: User, session_id: uuid.UUID) -> bool:
    s = db.get(UserSession, session_id)
    if s is None or s.user_id != user.id or s.revoked_at is not None:
        return False
    s.revoked_at = utcnow()
    audit_service.record_audit_event(
        db, action="session.revoked", resource_type="user", resource_id=user.id, actor=user,
        metadata={"session_id": str(session_id)},
    )
    return True
