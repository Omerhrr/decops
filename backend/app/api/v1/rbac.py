"""RBAC inspection endpoints (Phase 3): roles with their permissions, and the
permission catalogue. Reading the matrix requires users.manage; assigning
roles is handled by the users router (roles.assign)."""

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, require_permission
from app.models import Permission, Role
from app.schemas.admin import PermissionListPage, PermissionOut, RoleListPage, RoleOut

router = APIRouter(prefix="/roles", tags=["Roles"])


def _role_out(role: Role) -> RoleOut:
    return RoleOut(
        id=role.id,
        name=role.name,
        description=role.description,
        is_system_role=role.is_system_role,
        permissions=[link.permission.code for link in role.permissions],
    )


@router.get("", dependencies=[Depends(require_permission("users.manage", "roles.assign"))])
def list_roles(db: DbSession) -> RoleListPage:
    roles = db.query(Role).order_by(Role.name).all()
    return RoleListPage(items=[_role_out(r) for r in roles], total=len(roles))


@router.get("/permissions", dependencies=[Depends(require_permission("users.manage"))])
def list_permissions(db: DbSession) -> PermissionListPage:
    permissions = db.query(Permission).order_by(Permission.code).all()
    return PermissionListPage(
        items=[PermissionOut.model_validate(p) for p in permissions],
        total=len(permissions),
    )
