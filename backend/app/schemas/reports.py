"""Report & export schemas (MOD-007, Phase 7).

Reports are authorization-aware: `reports.view` holders get trends over the
tasks they may view; `reports.department.view` holders (department leads) are
scoped to their own departments. Exports additionally require
`exports.approved` (spec RBAC matrix: Read-Only Auditor) and every exported
row passes the same access engine as the on-screen register.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


# ---------- Requests ----------
class ExportRequest(BaseModel):
    export_type: str = Field(pattern="^(task_register|department_workload|task_completion)$")
    format: str = Field(default="csv", pattern="^(csv|pdf)$")
    # Optional register filters (task_register only)
    status: str | None = None
    priority: str | None = None
    department_id: uuid.UUID | None = None
    q: str | None = Field(default=None, max_length=200)
    # task_completion window
    weeks: int = Field(default=12, ge=1, le=52)


# ---------- Responses ----------
class CompletionWeekPoint(BaseModel):
    week_start: date
    completed: int
    created: int


class MilestoneProgress(BaseModel):
    total: int
    completed: int
    in_progress: int
    pending: int
    cancelled: int


class BlockerAnalysis(BaseModel):
    blocked_total: int
    by_priority: dict[str, int] = {}
    by_department: dict[str, int] = {}
    overdue_blocked: int  # blocked AND past due


class TaskCompletionReport(BaseModel):
    weeks: int
    series: list[CompletionWeekPoint]
    totals: dict[str, int]
    avg_days_to_complete: float | None
    by_status: dict[str, int]
    milestone_progress: MilestoneProgress
    blocker_analysis: BlockerAnalysis


class DepartmentWorkloadRow(BaseModel):
    department_id: uuid.UUID
    department_name: str
    lead: str | None = None
    member_count: int
    active_tasks: int
    overdue_tasks: int
    blocked_tasks: int
    completed_tasks: int
    open_assignments: int


class DepartmentWorkloadReport(BaseModel):
    departments: list[DepartmentWorkloadRow]
    scope: str  # "all" | "my_departments"
