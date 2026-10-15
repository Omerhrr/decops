"""Dashboard & report schemas (MOD-007, Phase 7; spec api.endpoint_groups
"Dashboards and Reports").

Every aggregate in this module is computed over the *authorized* task set -
the same access-engine decisions that gate the task register (exit criteria:
"Dashboard totals reconcile with authorized task records", "Restricted
information does not leak through reports"). Rows embedded in dashboard
responses (upcoming deadlines, blocked work, recent activity) therefore only
ever carry task data the requesting actor may view.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.tasks import TaskOut, TaskUserBrief


# ---------- Personal ----------
class PersonalSummary(BaseModel):
    assigned_active: int = 0        # active accountable/supporting PM assignments
    accountable_active: int = 0     # tasks where I am the accountable PM
    overdue: int = 0                # my active tasks past due
    blocked: int = 0                # my active tasks in blocked status
    due_soon: int = 0               # active tasks due within 7 days


class StatusBreakdown(BaseModel):
    draft: int = 0
    open: int = 0
    in_progress: int = 0
    blocked: int = 0
    under_review: int = 0
    completed: int = 0
    cancelled: int = 0
    archived: int = 0


class ManagementOverview(BaseModel):
    """Company-wide aggregates - only populated for dashboards.view holders.

    Totals cover every task the requesting administrator is authorized to
    view (tasks.manage_all => the whole register; others => their subset).
    """

    total_visible: int
    active: int
    overdue: int
    blocked: int
    completion_rate: int           # percent, completed / (completed + active), 0 when none
    completed_this_week: int
    by_status: StatusBreakdown


class UpcomingDeadlineRow(BaseModel):
    task_id: uuid.UUID
    task_number: str
    title: str
    due_date: date
    days_left: int
    status: str
    priority: str
    accountable_pm: TaskUserBrief | None = None


class BlockedTaskRow(UpcomingDeadlineRow):
    pass


class ActivityRow(BaseModel):
    task_id: uuid.UUID
    task_number: str
    task_title: str
    activity_type: str
    summary: str
    actor: TaskUserBrief | None = None
    created_at: datetime


class TrendPoint(BaseModel):
    week_start: date
    created: int
    completed: int


class DepartmentLoad(BaseModel):
    name: str
    total: int
    active: int


class DashboardCharts(BaseModel):
    trend: list[TrendPoint] = []
    by_priority: dict[str, int] = {}
    by_department: list[DepartmentLoad] = []


class DashboardSummary(BaseModel):
    me: PersonalSummary
    visible_totals: StatusBreakdown
    visible_total: int
    overdue_total: int
    blocked_total: int
    upcoming_deadlines: list[UpcomingDeadlineRow] = []
    blocked_tasks: list[BlockedTaskRow] = []
    recent_activity: list[ActivityRow] = []
    management_overview: ManagementOverview | None = None
    charts: DashboardCharts = DashboardCharts()


class MyTaskPage(BaseModel):
    items: list[TaskOut]
    total: int
    page: int
    page_size: int
    scope: str
