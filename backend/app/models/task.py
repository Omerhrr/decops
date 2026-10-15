"""Task models (spec data_model: tasks, task_assignments, task_departments,
task_access_grants; Phase 4 adds task_activities for the activity timeline).

Every task carries an explicit, self-contained access policy (visibility_mode
+ grants) evaluated by app.domain.access_policy. Task content is protected by
resource-level authorization, never by identifier secrecy alone (AC-10).
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow
from app.db.types import JSONType, UTCDateTime
from app.domain.task_lifecycle import TaskStatus


class TaskPriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ProgressMode(str, enum.Enum):
    """AC-06: progress calculation method is explicit and visible."""

    manual = "manual"
    calculated = "calculated"


class Task(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tasks"

    task_number: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    priority: Mapped[TaskPriority] = mapped_column(
        String(20), default=TaskPriority.medium, nullable=False, index=True
    )
    status: Mapped[TaskStatus] = mapped_column(
        String(20), default=TaskStatus.draft, nullable=False, index=True
    )

    # DEC-02: exactly one accountable PM (also mirrored in task_assignments)
    accountable_pm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    next_follow_up_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    percent_complete: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress_mode: Mapped[ProgressMode] = mapped_column(
        String(20), default=ProgressMode.manual, nullable=False
    )

    dependency_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachment_folder_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Phase 8 CSV migration: source identifier preserved for traceability and
    # retry-safe imports ("Task ID" -> task_number when reusable, else stored
    # here). Indexed; uniqueness is enforced by the import service, which must
    # recognise already-committed legacy rows instead of duplicating them.
    legacy_external_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Explicit, self-contained access policy (spec task_visibility.rules)
    visibility_mode: Mapped[str] = mapped_column(String(30), nullable=False)

    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    # AC-18: optimistic concurrency for concurrent edits
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    accountable_pm = relationship("User", foreign_keys=[accountable_pm_id], lazy="joined")
    created_by = relationship("User", foreign_keys=[created_by_id], lazy="joined")
    assignments = relationship(
        "TaskAssignment", back_populates="task", lazy="selectin",
        foreign_keys="TaskAssignment.task_id",
    )
    task_departments = relationship(
        "TaskDepartment", back_populates="task", lazy="selectin",
        cascade="all, delete-orphan",
    )
    access_grants = relationship(
        "TaskAccessGrant", back_populates="task", lazy="selectin",
        cascade="all, delete-orphan",
    )
    activities = relationship(
        "TaskActivity", back_populates="task", lazy="noload",
        cascade="all, delete-orphan",
    )


class AssignmentRoleType(str, enum.Enum):
    accountable_pm = "accountable_pm"
    supporting_pm = "supporting_pm"
    work_item_assignee = "work_item_assignee"


class TaskAssignment(UUIDPrimaryKeyMixin, Base):
    """Assignment record; the assigning user is always recorded (MOD-003)."""

    __tablename__ = "task_assignments"

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    assignment_role: Mapped[AssignmentRoleType] = mapped_column(String(30), nullable=False)
    assigned_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    task = relationship("Task", back_populates="assignments", foreign_keys=[task_id])
    user = relationship("User", foreign_keys=[user_id], lazy="joined")
    assigned_by = relationship("User", foreign_keys=[assigned_by_id], lazy="joined")

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


class ParticipationType(str, enum.Enum):
    executing = "executing"
    consulted = "consulted"
    informed = "informed"


class TaskDepartment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "task_departments"
    __table_args__ = (
        UniqueConstraint("task_id", "department_id", name="uq_task_department"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("departments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    participation_type: Mapped[ParticipationType] = mapped_column(
        String(20), default=ParticipationType.executing, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)

    task = relationship("Task", back_populates="task_departments")
    department = relationship("Department", lazy="joined")


class AccessLevel(str, enum.Enum):
    view = "view"
    operate = "operate"
    manage = "manage"
    # A recorded, structural denial (deny overrides any grant, AC-10)
    denied = "denied"


class TaskAccessGrant(UUIDPrimaryKeyMixin, Base):
    """Explicit per-user grant/denial; revocable with recorded reason."""

    __tablename__ = "task_access_grants"

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    principal_type: Mapped[str] = mapped_column(String(20), default="user", nullable=False)
    principal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    access_level: Mapped[AccessLevel] = mapped_column(String(20), nullable=False)
    granted_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    task = relationship("Task", back_populates="access_grants")
    principal = relationship("User", foreign_keys=[principal_id], lazy="joined")
    granted_by = relationship("User", foreign_keys=[granted_by_id], lazy="joined")

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


class TaskActivity(UUIDPrimaryKeyMixin, Base):
    """Append-only, user-facing activity timeline shown on the task detail page.

    Distinct from admin audit_events: visible to task-authorized users, records
    the human story (who did what, when, why) of one task only.
    """

    __tablename__ = "task_activities"

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    activity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSONType(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)

    task = relationship("Task", back_populates="activities")
    actor = relationship("User", foreign_keys=[actor_id], lazy="joined")
