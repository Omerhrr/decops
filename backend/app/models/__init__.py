"""All SQLAlchemy models are imported here so Alembic autogenerate and
create_all see the complete metadata."""

from app.models.audit import AuditEvent
from app.models.collaboration import (
    Attachment,
    Comment,
    Notification,
    NotificationPreference,
    OutboxEvent,
    OutboxStatus,
)
from app.models.department import Department, DepartmentMembership, DepartmentStatus, MembershipRole
from app.models.import_job import ImportJob, ImportJobStatus
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
from app.models.workflow import (
    ProgressBasis,
    StageExecutionMode,
    StageStatus,
    TaskStage,
    WorkItem,
    WorkItemDependency,
    WorkItemStatus,
    WorkItemType,
    WorkflowTemplate,
)

__all__ = [
    "AccessLevel",
    "AccountStatus",
    "AssignmentRoleType",
    "Attachment",
    "AuditEvent",
    "Comment",
    "Department",
    "DepartmentMembership",
    "DepartmentStatus",
    "ImportJob",
    "ImportJobStatus",
    "MembershipRole",
    "Notification",
    "NotificationPreference",
    "OutboxEvent",
    "OutboxStatus",
    "ParticipationType",
    "Permission",
    "ProgressBasis",
    "ProgressMode",
    "Role",
    "RolePermission",
    "ScopeType",
    "StageExecutionMode",
    "StageStatus",
    "Task",
    "TaskAccessGrant",
    "TaskActivity",
    "TaskAssignment",
    "TaskDepartment",
    "TaskPriority",
    "TaskStage",
    "User",
    "UserRole",
    "UserSession",
    "WorkItem",
    "WorkItemDependency",
    "WorkItemStatus",
    "WorkItemType",
    "WorkflowTemplate",
]
