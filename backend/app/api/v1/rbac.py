"""RBAC inspection and role administration endpoints.

Reading the matrix requires users.manage or roles.assign; assigning roles to
users is handled by the users router (roles.assign). Creating and editing
custom roles also requires roles.assign. System roles are fixed and stay
read-only so RBAC guarantees cannot be silently weakened.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

import uuid

from app.api.deps import CurrentUser, DbSession, require_permission
from app.core.context import current_request_id
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.models import Permission, Role, RolePermission, UserRole
from app.schemas.admin import (
    PermissionListPage,
    PermissionOut,
    RoleListPage,
    RoleOut,
    RoleWriteRequest,
)
from app.services import audit_service

router = APIRouter(prefix="/roles", tags=["Roles"])

ROLE_ADMIN_PERMISSIONS = ("roles.assign", "users.manage")


def _auth(request: Request, user: CurrentUser) -> None:
    request.state.user = user


def _role_out(role: Role) -> RoleOut:
    return RoleOut(
        id=role.id,
        name=role.name,
        description=role.description,
        is_system_role=role.is_system_role,
        permissions=[link.permission.code for link in role.permissions],
    )


def _load_role(db: DbSession, role_id: uuid.UUID) -> Role:
    role = db.get(Role, role_id)
    if role is None:
        raise NotFoundError("Role not found.")
    return role


def _resolve_permissions(db: DbSession, codes: list[str]) -> list[Permission]:
    unique = sorted(set(codes))
    if len(unique) != len(codes):
        raise ValidationFailedError("Duplicate permission codes are not allowed.")
    rows = list(db.scalars(select(Permission).where(Permission.code.in_(unique))).all())
    found = {p.code for p in rows}
    missing = [c for c in unique if c not in found]
    if missing:
        raise ValidationFailedError(f"Unknown permission code(s): {', '.join(missing)}.")
    return rows


@router.get("", dependencies=[Depends(require_permission(*ROLE_ADMIN_PERMISSIONS))])
def list_roles(db: DbSession) -> RoleListPage:
    roles = db.query(Role).order_by(Role.name).all()
    return RoleListPage(items=[_role_out(r) for r in roles], total=len(roles))


@router.get("/permissions", dependencies=[Depends(require_permission(*ROLE_ADMIN_PERMISSIONS))])
def list_permissions(db: DbSession) -> PermissionListPage:
    permissions = db.query(Permission).order_by(Permission.code).all()
    return PermissionListPage(
        items=[PermissionOut.model_validate(p) for p in permissions],
        total=len(permissions),
    )


@router.post("", response_model=RoleOut,
             status_code=201,
             dependencies=[Depends(require_permission("roles.assign"))])
def create_role(
    request: Request, db: DbSession, user: CurrentUser, body: RoleWriteRequest,
) -> RoleOut:
    _auth(request, user)
    if body.name is None:
        raise ValidationFailedError("Role name is required.")
    name = body.name.strip()
    if not name:
        raise ValidationFailedError("Role name is required.")
    if db.scalar(select(Role).where(Role.name == name)) is not None:
        raise ConflictError("A role with this name already exists.")
    permissions = _resolve_permissions(db, body.permissions)
    role = Role(name=name, description=body.description, is_system_role=False)
    role.permissions = [
        RolePermission(role_id=role.id, permission_id=p.id) for p in permissions
    ]
    db.add(role)
    db.flush()
    audit_service.record_audit_event(
        db,
        action="role.created",
        resource_type="role",
        resource_id=role.id,
        actor=user,
        request_id=current_request_id(),
        change_summary=f"Custom role '{name}' created with {len(permissions)} permission(s)",
        metadata={"name": name, "permissions": sorted(p.code for p in permissions)},
    )
    db.commit()
    db.refresh(role)
    return _role_out(role)


@router.patch("/{role_id}", response_model=RoleOut,
              dependencies=[Depends(require_permission("roles.assign"))])
def update_role(
    request: Request, db: DbSession, user: CurrentUser,
    role_id: uuid.UUID, body: RoleWriteRequest,
) -> RoleOut:
    _auth(request, user)
    role = _load_role(db, role_id)
    if role.is_system_role:
        raise ValidationFailedError(
            "System roles are read-only. Create a custom role to customize permissions."
        )
    changed = []
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise ValidationFailedError("Role name is required.")
        clash = db.scalar(select(Role).where(Role.name == name, Role.id != role.id))
        if clash is not None:
            raise ConflictError("A role with this name already exists.")
        if name != role.name:
            role.name = name
            changed.append("name")
    if body.description is not None:
        role.description = body.description
        changed.append("description")
    if body.permissions is not None:
        permissions = _resolve_permissions(db, body.permissions)
        role.permissions = [
            RolePermission(role_id=role.id, permission_id=p.id) for p in permissions
        ]
        changed.append("permissions")
    db.flush()
    audit_service.record_audit_event(
        db,
        action="role.updated",
        resource_type="role",
        resource_id=role.id,
        actor=user,
        request_id=current_request_id(),
        change_summary=f"Custom role '{role.name}' updated ({', '.join(changed) or 'no changes'})",
        metadata={"name": role.name, "changed": changed},
    )
    db.commit()
    db.refresh(role)
    return _role_out(role)


@router.delete("/{role_id}", status_code=204,
               dependencies=[Depends(require_permission("roles.assign"))])
def delete_role(request: Request, db: DbSession, user: CurrentUser, role_id: uuid.UUID) -> None:
    _auth(request, user)
    role = _load_role(db, role_id)
    if role.is_system_role:
        raise ValidationFailedError("System roles cannot be deleted.")
    in_use = db.query(UserRole).filter(UserRole.role_id == role.id).count()
    if in_use:
        raise ConflictError(
            f"This role is assigned to {in_use} user(s). Revoke it before deleting."
        )
    audit_service.record_audit_event(
        db,
        action="role.deleted",
        resource_type="role",
        resource_id=role.id,
        actor=user,
        request_id=current_request_id(),
        change_summary=f"Custom role '{role.name}' deleted",
        metadata={"name": role.name},
    )
    db.delete(role)
    db.commit()
