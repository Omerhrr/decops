"""Workflow models (spec data_model: task_stages, work_items,
workflow_dependencies; Phase 5 — Workflow Engine).

Structure (spec workflow_engine.structure): Task → Stage → Milestone/Subtask.
- Stages order work into phases; each stage declares an execution_mode
  (sequential stages gate on predecessor completion, parallel stages may run
  simultaneously — mixed workflows are simply a combination).
- Work items (milestones and subtasks) are the assignable units; subtasks may
  nest under milestones. Dependencies connect work items within a task
  (within or across stages); cycles are rejected at the domain layer.
- Completed work items retain their completion history (completed_at +
  task_activities + audit_events); nothing is destroyed implicitly.
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow
from app.db.types import JSONType, UTCDateTime


class StageExecutionMode(str, enum.Enum):
    sequential = "sequential"
    parallel = "parallel"


class StageStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class WorkItemType(str, enum.Enum):
    milestone = "milestone"
    subtask = "subtask"


class WorkItemStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class ProgressBasis(str, enum.Enum):
    """Which work items contribute to a stage's calculated progress
    (spec progress_calculation: "Define whether milestones or subtasks
    contribute to progress")."""

    all_items = "all_items"
    milestones_only = "milestones_only"
    subtasks_only = "subtasks_only"


class TaskStage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "task_stages"
    __table_args__ = (
        UniqueConstraint("task_id", "sequence_number", name="uq_stage_task_sequence"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Strict ordering within the task; sequential stages gate on all
    # lower-numbered stages being completed/cancelled.
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    execution_mode: Mapped[StageExecutionMode] = mapped_column(
        String(20), default=StageExecutionMode.sequential, nullable=False
    )
    status: Mapped[StageStatus] = mapped_column(
        String(20), default=StageStatus.pending, nullable=False, index=True
    )

    # Relative contribution to task progress (weight > 0).
    weight: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    progress_basis: Mapped[ProgressBasis] = mapped_column(
        String(20), default=ProgressBasis.all_items, nullable=False
    )

    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    task = relationship("Task", foreign_keys=[task_id])

    @property
    def is_done(self) -> bool:
        status = self.status.value if hasattr(self.status, "value") else str(self.status)
        return status in {"completed", "cancelled"}


class WorkItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "work_items"
    __table_args__ = (
        UniqueConstraint("stage_id", "sequence_number", name="uq_item_stage_sequence"),
        Index("ix_work_items_task_status", "task_id", "status"),
        Index("ix_work_items_assignee", "assigned_user_id"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    stage_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("task_stages.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Subtasks may nest under a milestone (one level); milestones are top-level.
    parent_work_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("work_items.id", ondelete="CASCADE"), index=True, nullable=True
    )
    item_type: Mapped[WorkItemType] = mapped_column(String(20), nullable=False)

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[WorkItemStatus] = mapped_column(
        String(20), default=WorkItemStatus.pending, nullable=False, index=True
    )
    priority: Mapped[str | None] = mapped_column(String(20), nullable=True)

    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Optional items are excluded from progress calculation and stage completion.
    is_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    weight: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    # AC-18: optimistic concurrency on editable work items.
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    stage = relationship("TaskStage", foreign_keys=[stage_id])
    assignee = relationship("User", foreign_keys=[assigned_user_id], lazy="joined")
    assigned_by = relationship("User", foreign_keys=[assigned_by_id])
    parent = relationship("WorkItem", remote_side="WorkItem.id", foreign_keys=[parent_work_item_id])

    @property
    def is_done(self) -> bool:
        status = self.status.value if hasattr(self.status, "value") else str(self.status)
        return status in {"completed", "cancelled"}


class WorkItemDependency(UUIDPrimaryKeyMixin, Base):
    """Directed edge: `successor` cannot start until `predecessor` completes.

    Dependencies connect work items within one task (within or across stages);
    the denormalized task_id makes per-task graph loading and cross-task
    rejection cheap. Cycles are rejected by the domain layer.
    """

    __tablename__ = "work_item_dependencies"
    __table_args__ = (
        UniqueConstraint("predecessor_id", "successor_id", name="uq_dependency_edge"),
        Index("ix_dependency_successor", "successor_id"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    predecessor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_items.id", ondelete="CASCADE"), index=True, nullable=False
    )
    successor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_items.id", ondelete="CASCADE"), index=True, nullable=False
    )
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)

    predecessor = relationship("WorkItem", foreign_keys=[predecessor_id], lazy="joined")
    successor = relationship("WorkItem", foreign_keys=[successor_id], lazy="joined")


class WorkflowTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Reusable workflow blueprints (spec data_model.workflow_templates;
    Administration page lists them). `definition` JSON shape:
    {"stages": [{"name", "execution_mode", "weight", "items":
                 [{"item_type", "title", "is_required", "weight"}]}]}
    """

    __tablename__ = "workflow_templates"

    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    definition: Mapped[dict] = mapped_column(JSONType(), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_by = relationship("User", foreign_keys=[created_by_id], lazy="joined")
