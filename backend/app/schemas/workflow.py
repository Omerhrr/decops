"""Workflow API schemas."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.workflow import ProgressBasis, StageExecutionMode, WorkItemType

EXECUTION_MODES = ("sequential", "parallel")
ITEM_TYPES = ("milestone", "subtask")


# ---------- Requests ----------
class StageCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    # Explicit placement or append to the end when omitted.
    sequence_number: int | None = Field(default=None, ge=1, le=999)
    execution_mode: StageExecutionMode = StageExecutionMode.sequential
    weight: int = Field(default=1, ge=1, le=100)
    progress_basis: ProgressBasis = ProgressBasis.all_items
    start_date: date | None = None
    due_date: date | None = None

    @model_validator(mode="after")
    def _check_dates(self) -> "StageCreateRequest":
        if self.start_date and self.due_date and self.due_date < self.start_date:
            raise ValueError("due_date cannot be before start_date")
        return self


class StageUpdateRequest(BaseModel):
    """Partial update; `version` reserved for future stage-level locking."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    sequence_number: int | None = Field(default=None, ge=1, le=999)
    execution_mode: StageExecutionMode | None = None
    weight: int | None = Field(default=None, ge=1, le=100)
    progress_basis: ProgressBasis | None = None
    start_date: date | None = None
    due_date: date | None = None


class StageTransitionRequest(BaseModel):
    to_status: str
    reason: str | None = Field(default=None, max_length=2000)


class WorkItemCreateRequest(BaseModel):
    item_type: WorkItemType
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=20000)
    parent_work_item_id: uuid.UUID | None = None
    sequence_number: int | None = Field(default=None, ge=1, le=999)
    priority: str | None = Field(default=None, max_length=20)
    assigned_user_id: uuid.UUID | None = None
    is_required: bool = True
    weight: int = Field(default=1, ge=1, le=100)
    start_date: date | None = None
    due_date: date | None = None

    @model_validator(mode="after")
    def _check_dates(self) -> "WorkItemCreateRequest":
        if self.start_date and self.due_date and self.due_date < self.start_date:
            raise ValueError("due_date cannot be before start_date")
        return self


class WorkItemUpdateRequest(BaseModel):
    """Partial update; `version` required (optimistic concurrency)."""

    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=20000)
    priority: str | None = Field(default=None, max_length=20)
    sequence_number: int | None = Field(default=None, ge=1, le=999)
    is_required: bool | None = None
    weight: int | None = Field(default=None, ge=1, le=100)
    start_date: date | None = None
    due_date: date | None = None
    version: int = Field(ge=1)


class WorkItemTransitionRequest(BaseModel):
    to_status: str
    reason: str | None = Field(default=None, max_length=2000)


class WorkItemAssignRequest(BaseModel):
    assigned_user_id: uuid.UUID | None = None  # null clears the assignment


class DependencyCreateRequest(BaseModel):
    predecessor_id: uuid.UUID
    successor_id: uuid.UUID
    note: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _check_distinct(self) -> "DependencyCreateRequest":
        if self.predecessor_id == self.successor_id:
            raise ValueError("A work item cannot depend on itself")
        return self


class ProgressModeRequest(BaseModel):
    """Switch between manual and calculated task progress."""

    progress_mode: str
    reason: str | None = Field(default=None, max_length=2000)

    @field_validator("progress_mode")
    @classmethod
    def _check_mode(cls, v: str) -> str:
        if v not in ("manual", "calculated"):
            raise ValueError("progress_mode must be 'manual' or 'calculated'")
        return v


class WorkflowTemplateItemDef(BaseModel):
    item_type: WorkItemType = WorkItemType.subtask
    title: str = Field(min_length=1, max_length=300)
    is_required: bool = True
    weight: int = Field(default=1, ge=1, le=100)


class WorkflowTemplateStageDef(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    execution_mode: StageExecutionMode = StageExecutionMode.sequential
    weight: int = Field(default=1, ge=1, le=100)
    items: list[WorkflowTemplateItemDef] = []


class WorkflowTemplateCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    stages: list[WorkflowTemplateStageDef] = Field(min_length=1)


class WorkflowTemplateUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    stages: list[WorkflowTemplateStageDef] | None = None
    is_active: bool | None = None


# ---------- Responses ----------
class StageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    name: str
    description: str | None = None
    sequence_number: int
    execution_mode: str
    status: str
    weight: int
    progress_basis: str
    start_date: date | None = None
    due_date: date | None = None
    completed_at: datetime | None = None


class WorkItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    stage_id: uuid.UUID
    parent_work_item_id: uuid.UUID | None = None
    item_type: str
    title: str
    description: str | None = None
    status: str
    priority: str | None = None
    assigned_user_id: uuid.UUID | None = None
    assignee: "TaskUserBrief | None" = None
    sequence_number: int
    is_required: bool
    weight: int
    start_date: date | None = None
    due_date: date | None = None
    completed_at: datetime | None = None
    version: int


class DependencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    predecessor_id: uuid.UUID
    successor_id: uuid.UUID
    note: str | None = None


class StageProgressOut(BaseModel):
    stage_id: str
    stage_name: str
    status: str
    weight: int
    included_item_count: int
    completed_item_count: int
    total_weight: int
    completed_weight: int
    percent: int
    excluded: dict[str, int] = {}
    method: str


class WorkflowProgressOut(BaseModel):
    task_percent: int
    counted_item_total: int
    counted_item_completed: int
    method: str
    stages: list[StageProgressOut]


class BlockerOut(BaseModel):
    item_id: str
    blocked_by: list[str]


class WorkflowOut(BaseModel):
    """The full workflow tree of one task: stages, items, dependencies,
    blockers and the progress calculation with its method."""

    task_id: uuid.UUID
    task_status: str
    task_progress_mode: str
    task_percent_complete: int
    calculated_percent: int
    stages: list[StageOut]
    items: list[WorkItemOut]
    dependencies: list[DependencyOut]
    blockers: list[BlockerOut]
    actionable_stage_ids: list[str]
    progress: WorkflowProgressOut


class WorkflowTemplatesOut(BaseModel):
    items: list["WorkflowTemplateOut"]
    total: int


class WorkflowTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None
    definition: dict
    version: int
    is_active: bool
    created_by_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


from app.schemas.tasks import TaskUserBrief  # noqa: E402  (avoids circular import at module load)

WorkItemOut.model_rebuild()
WorkflowTemplatesOut.model_rebuild()
