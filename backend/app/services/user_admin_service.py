"""User administration service : employee lifecycle, role assignment,
and audited permission changes (exit criterion: "Permission changes
are audited")."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.base import utcnow
from app.models import AccountStatus, Role, User, UserRole, UserSession
from app.services import audit_service

MIN_PASSWORD_LENGTH = 10


class UserAdminError(Exception):
    def __init__(self, message: str, *, code: str = "user_admin_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def get_by_id(db: Session, user_id: uuid.UUID) -> User | None:
    return db.get(User, user_id)


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.strip().lower()))


def create_user(
    db: Session,
    *,
    actor: User | None,
    email: str,
    full_name: str,
    employee_code: str,
    password: str,
    role_ids: list[uuid.UUID] | None = None,
    request_id: str | None = None,
) -> User:
    """Create an employee with locally managed credentials."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise UserAdminError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
            code="weak_password",
        )
    normalized_email = email.strip().lower()
    if get_by_email(db, normalized_email) is not None:
        raise UserAdminError("A user with this email already exists.", code="email_taken")
    if db.scalar(select(User).where(User.employee_code == employee_code.strip())):
        raise UserAdminError("An employee with this code already exists.", code="employee_code_taken")

    user = User(
        employee_code=employee_code.strip(),
        full_name=full_name.strip(),
        email=normalized_email,
        authentication_reference=hash_password(password),
        account_status=AccountStatus.active,
    )
    db.add(user)
    db.flush()

    for role_id in role_ids or []:
        role = db.get(Role, role_id)
        if role is None:
            raise UserAdminError("One of the selected roles does not exist.", code="role_not_found")
        db.add(UserRole(user_id=user.id, role_id=role.id, scope_type="global", granted_by=actor.id if actor else None))

    audit_service.record_audit_event(
        db,
        action="user.created",
        resource_type="user",
        resource_id=user.id,
        actor=actor,
        request_id=request_id,
        change_summary=f"Created employee {user.full_name} ({user.email})",
        metadata={"employee_code": user.employee_code, "role_ids": [str(r) for r in role_ids or []]},
    )
    return user


def update_user(
    db: Session,
    *,
    actor: User | None,
    user: User,
    full_name: str | None = None,
    email: str | None = None,
    request_id: str | None = None,
) -> User:
    """Update permitted profile fields; every change is recorded in the audit trail."""
    changes: dict[str, dict] = {}
    if email is not None:
        normalized = email.strip().lower()
        if normalized != user.email:
            existing = get_by_email(db, normalized)
            if existing is not None and existing.id != user.id:
                raise UserAdminError("A user with this email already exists.", code="email_taken")
            changes["email"] = {"from": user.email, "to": normalized}
            user.email = normalized
    if full_name is not None and full_name.strip() != user.full_name:
        changes["full_name"] = {"from": user.full_name, "to": full_name.strip()}
        user.full_name = full_name.strip()

    if changes:
        audit_service.record_audit_event(
            db,
            action="user.updated",
            resource_type="user",
            resource_id=user.id,
            actor=actor,
            request_id=request_id,
            change_summary=", ".join(f"{k} changed" for k in changes),
            metadata={"changes": changes},
        )
    return user


def _status_value(status) -> str:
    """account_status may be an AccountStatus enum or a plain string depending
    on the backend/driver - normalize before comparing or summarizing."""
    return status.value if hasattr(status, "value") else str(status)


def set_account_status(
    db: Session,
    *,
    actor: User | None,
    user: User,
    status: AccountStatus,
    reason: str | None = None,
    request_id: str | None = None,
) -> User:
    """Deactivate/disable/reactivate an employee. Deactivation immediately
    invalidates all their sessions."""
    if _status_value(user.account_status) == _status_value(status):
        return user
    previous = _status_value(user.account_status)
    user.account_status = status
    if status != AccountStatus.active:
        now = utcnow()
        for session in db.scalars(
            select(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        ).all():
            session.revoked_at = now

    audit_service.record_audit_event(
        db,
        action="user.status_changed",
        resource_type="user",
        resource_id=user.id,
        actor=actor,
        request_id=request_id,
        reason=reason,
        change_summary=f"Account status {previous} -> {_status_value(status)}",
        metadata={"from": previous, "to": _status_value(status), "sessions_revoked": status != AccountStatus.active},
    )
    return user


def assign_global_role(
    db: Session,
    *,
    actor: User | None,
    user: User,
    role: Role,
    request_id: str | None = None,
) -> UserRole:
    """Grant a global role. Permission changes are audited (exit criteria)."""
    existing = db.scalar(
        select(UserRole).where(
            UserRole.user_id == user.id,
            UserRole.role_id == role.id,
            UserRole.scope_type == "global",
        )
    )
    if existing is not None:
        return existing
    link = UserRole(
        user_id=user.id, role_id=role.id, scope_type="global", granted_by=actor.id if actor else None
    )
    db.add(link)
    db.flush()
    audit_service.record_audit_event(
        db,
        action="rbac.role_assigned",
        resource_type="user",
        resource_id=user.id,
        actor=actor,
        request_id=request_id,
        change_summary=f"Assigned global role '{role.name}'",
        metadata={"role_id": str(role.id), "role_name": role.name, "scope": "global"},
    )
    return link


def revoke_global_role(
    db: Session,
    *,
    actor: User | None,
    user: User,
    role: Role,
    request_id: str | None = None,
) -> None:
    """Revoke a global role. Takes effect on the next authorization check."""
    link = db.scalar(
        select(UserRole).where(
            UserRole.user_id == user.id,
            UserRole.role_id == role.id,
            UserRole.scope_type == "global",
        )
    )
    if link is None:
        return
    db.delete(link)
    db.flush()
    audit_service.record_audit_event(
        db,
        action="rbac.role_revoked",
        resource_type="user",
        resource_id=user.id,
        actor=actor,
        request_id=request_id,
        change_summary=f"Revoked global role '{role.name}'",
        metadata={"role_id": str(role.id), "role_name": role.name, "scope": "global"},
    )
