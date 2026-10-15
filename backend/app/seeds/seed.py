"""Idempotent seed script: system roles + permissions from the approved role
matrix, plus the initial administrator account.

Run with: uv run python -m app.seeds.seed
Safe to run repeatedly.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import Permission, Role, RolePermission, User, UserRole
from app.seeds.rbac_matrix import AUTHENTICATED_PERMISSIONS, ROLE_MATRIX

logger = logging.getLogger("decops.seed")


def seed_permissions_and_roles(db: Session) -> None:
    permission_cache: dict[str, Permission] = {}

    def ensure_permission(code: str) -> Permission:
        if code in permission_cache:
            return permission_cache[code]
        perm = db.scalar(select(Permission).where(Permission.code == code))
        if perm is None:
            perm = Permission(code=code, description=code)
            db.add(perm)
            db.flush()
        permission_cache[code] = perm
        return perm

    # Baseline permissions every authenticated user receives
    for code in AUTHENTICATED_PERMISSIONS:
        ensure_permission(code)

    for role_name, spec in ROLE_MATRIX.items():
        role = db.scalar(select(Role).where(Role.name == role_name))
        if role is None:
            role = Role(name=role_name, description=spec["description"], is_system_role=True)
            db.add(role)
            db.flush()
        for perm_code in spec["permissions"]:
            perm = ensure_permission(perm_code)
            exists = any(rp.permission_id == perm.id for rp in role.permissions)
            if not exists:
                db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.flush()


def seed_admin(db: Session) -> None:
    email = settings.seed_admin_email.lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            employee_code=settings.seed_admin_employee_code,
            full_name=settings.seed_admin_name,
            email=email,
            authentication_reference=hash_password(settings.seed_admin_password),
            account_status="active",
        )
        db.add(user)
        db.flush()
        logger.info("seeded admin user %s", email)

    # Grant Company Administrator + System Administrator (global scope)
    for role_name in ("Company Administrator", "System Administrator"):
        role = db.scalar(select(Role).where(Role.name == role_name))
        if role is None:
            continue
        existing = db.query(UserRole).filter_by(
            user_id=user.id, role_id=role.id, scope_type="global"
        ).first()
        if existing is None:
            db.add(UserRole(user_id=user.id, role_id=role.id, scope_type="global"))


def run_seed() -> None:
    db = SessionLocal()
    try:
        seed_permissions_and_roles(db)
        seed_admin(db)
        db.commit()
        logger.info("seed complete")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_seed()
