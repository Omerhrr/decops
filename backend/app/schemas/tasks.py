"""Task API schemas (spec api.endpoint_groups.Tasks; strict validation)."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.task import AccessLevel, AssignmentRoleType, ParticipationType, TaskPriority
from app.models.task import ProgressMode as ProgressModeEnum

VISIBILITY_MODES = ("private", "participants", "department_scoped", "custom")


# ---------- Requests ----------
class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    description: str | None = Field(default=None, max_length=20000)
    priority: TaskPriority = TaskPriority.medium
    # AC-01: a task is created with an accountable PM
    accountable_pm_id: uuid.UUID
    start_date: date | None = None
    due_date: date | None = None
    next_follow_up_date: date | None = None
    dependency_summary: str | None = Field(default=None, max_length=5000)
    visibility_mode: str = "participants"
    progress_mode: ProgressModeEnum = ProgressModeEnum.manual
    department_ids: list[uuid.UUID] = []
    participation_type: ParticipationType = ParticipationType.executing
    # explicit per-user grants for custom/private/participants modes
    grant_user_ids: list[uuid.UUID] = []
    grant_access_level: AccessLevel = AccessLevel.view

    @field_validator("visibility_mode")
    @classmethod
    def _check_visibility(cls, v: str) -> str:
        if v not in VISIBILITY_MODES:
            raise ValueError(f"visibility_mode must be one of {', '.join(VISIBILITY_MODES)}")
        return v


class TaskUpdateRequest(BaseModel):
    """Partial update. `version` is required (AC-18 optimistic concurrency)."""

    title: str | None = Field(default=None, min_length=3, max_length=300)
    description: str | None = Field(default=None, max_length=20000)
    priority: TaskPriority | None = None
    start_date: date | None = None
    due_date: date | None = None
    next_follow_up_date: date | None = None
    percent_complete: int | None = Field(default=None, ge=0, le=100)
    progress_mode: ProgressModeEnum | None = None
    dependency_summary: str | None = Field(default=None, max_length=5000)
    version: int = Field(ge=1)


class TaskTransitionRequest(BaseModel):
    to_status: str
    reason: str | None = Field(default=None, max_length=2000)


class TaskAssignRequest(BaseModel):
    user_id: uuid.UUID
    assignment_role: AssignmentRoleType


class TaskDepartmentAddRequest(BaseModel):
    department_id: uuid.UUID
    participation_type: ParticipationType = ParticipationType.executing


class TaskAccessGrantRequest(BaseModel):
    user_id: uuid.UUID
    access_level: AccessLevel = AccessLevel.view


class AccessRevokeRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


# ---------- Responses ----------
class TaskUserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    email: str
    employee_code: str


class TaskAssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    user: TaskUserBrief
    assignment_role: AssignmentRoleType
    assigned_by_id: uuid.UUID
    assigned_at: datetime
    revoked_at: datetime | None = None


class TaskDepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    department_id: uuid.UUID
    department_name: str | None = None
    participation_type: ParticipationType


class TaskAccessGrantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    principal_id: uuid.UUID
    principal: TaskUserBrief
    access_level: AccessLevel
    granted_by_id: uuid.UUID
    granted_at: datetime
    revoked_at: datetime | None = None
    revocation_reason: str | None = None


class TaskActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    activity_type: str
    summary: str
    detail: dict | None = None
    created_at: datetime
    actor: TaskUserBrief | None = None


class TaskOut(BaseModel):
    """Task register row (spec frontend_pages.TaskRegister columns)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_number: str
    title: str
    priority: TaskPriority
    status: str
    accountable_pm_id: uuid.UUID
    accountable_pm: TaskUserBrief | None = None
    start_date: date | None = None
    due_date: date | None = None
    next_follow_up_date: date | None = None
    percent_complete: int
    progress_mode: ProgressModeEnum
    visibility_mode: str
    created_at: datetime
    department_names: list[str] = []


class TaskDetailOut(TaskOut):
    description: str | None = None
    created_by_id: uuid.UUID
    dependency_summary: str | None = None
    version: int
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    archived_at: datetime | None = None
    updated_at: datetime
    assignments: list[TaskAssignmentOut] = []
    task_departments: list[TaskDepartmentOut] = []
    access_grants: list[TaskAccessGrantOut] = []


class TaskPage(BaseModel):
    items: list[TaskOut]
    total: int
    page: int
    page_size: int


class TransitionOptionsOut(BaseModel):
    current_status: str
    allowed_transitions: list[str]
