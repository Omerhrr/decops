"""All SQLAlchemy models are imported here so Alembic autogenerate and
create_all see the complete metadata."""

from app.models.audit import AuditEvent
from app.models.department import Department, DepartmentMembership, DepartmentStatus, MembershipRole
from app.models.rbac import Permission, Role, RolePermission, ScopeType, UserRole
from app.models.task import (
    AccessLevel,
    AssignmentRoleType,
    ParticipationType,
    ProgressMode,
    Task,
    TaskAccessGrant,
    TaskActivity,
    TaskAssignment,
    TaskDepartment,
    TaskPriority,
)
from app.models.user import AccountStatus, User, UserSession

__all__ = [
    "AccessLevel",
    "AccountStatus",
    "AssignmentRoleType",
    "AuditEvent",
    "Department",
    "DepartmentMembership",
    "DepartmentStatus",
    "MembershipRole",
    "ParticipationType",
    "Permission",
    "ProgressMode",
    "Role",
    "RolePermission",
    "ScopeType",
    "Task",
    "TaskAccessGrant",
    "TaskActivity",
    "TaskAssignment",
    "TaskDepartment",
    "TaskPriority",
    "User",
    "UserRole",
    "UserSession",
]
