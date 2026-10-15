"""All SQLAlchemy models are imported here so Alembic autogenerate and
create_all see the complete metadata."""

from app.models.audit import AuditEvent
from app.models.department import Department, DepartmentMembership, DepartmentStatus, MembershipRole
from app.models.rbac import Permission, Role, RolePermission, ScopeType, UserRole
from app.models.user import AccountStatus, User, UserSession

__all__ = [
    "AccountStatus",
    "AuditEvent",
    "Department",
    "DepartmentMembership",
    "DepartmentStatus",
    "MembershipRole",
    "Permission",
    "Role",
    "RolePermission",
    "ScopeType",
    "User",
    "UserRole",
    "UserSession",
]
