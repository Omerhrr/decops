"""Dashboard endpoints.

Personal dashboards are available to every authenticated user - they only
ever surface that user's own authorized data. The management overview
block inside /dashboard/summary requires the `dashboards.view` permission
and still only aggregates authorized records.
"""

from typing import Literal

from fastapi import APIRouter, Query, Request

from app.api.deps import CurrentUser, DbSession
from app.schemas.dashboards import (
    BlockedTaskRow,
    DashboardSummary,
    MyTaskPage,
    UpcomingDeadlineRow,
)
from app.schemas.tasks import TaskOut, TaskUserBrief
from app.services import dashboard_service
from app.services.task_service import get_user_permission_codes

router = APIRouter(prefix="/dashboard", tags=["Dashboards"])


def _auth(request: Request, user: CurrentUser) -> None:
    request.state.user = user


def _out(task) -> dict:
    return TaskOut(
        id=task.id,
        task_number=task.task_number,
        title=task.title,
        priority=task.priority,
        status=str(getattr(task.status, "value", task.status)),
        accountable_pm_id=task.accountable_pm_id,
        accountable_pm=(
            TaskUserBrief.model_validate(task.accountable_pm) if task.accountable_pm else None
        ),
        start_date=task.start_date,
        due_date=task.due_date,
        next_follow_up_date=task.next_follow_up_date,
        percent_complete=task.percent_complete,
        progress_mode=task.progress_mode,
        visibility_mode=task.visibility_mode,
        created_at=task.created_at,
        department_names=[
            td.department.name for td in task.task_departments if td.department
        ],
    )


@router.get("/summary", response_model=DashboardSummary)
def get_summary(request: Request, db: DbSession, user: CurrentUser):
    _auth(request, user)
    codes = get_user_permission_codes(db, user)
    include_management = "dashboards.view" in codes
    return dashboard_service.dashboard_summary(db, user, include_management=include_management)


@router.get("/my-tasks", response_model=MyTaskPage)
def get_my_tasks(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    scope: Literal["assigned", "accountable", "all"] = Query("assigned"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
):
    _auth(request, user)
    items, total = dashboard_service.my_tasks(
        db, user, scope=scope, page=page, page_size=page_size
    )
    return MyTaskPage(
        items=[_out(t) for t in items],
        total=total,
        page=page,
        page_size=page_size,
        scope=scope,
    )


@router.get("/overdue", response_model=list[UpcomingDeadlineRow])
def get_overdue(request: Request, db: DbSession, user: CurrentUser):
    _auth(request, user)
    return [
        dashboard_service.deadline_row(t)
        for t in dashboard_service.overdue_tasks(db, user)
    ]


@router.get("/blocked", response_model=list[BlockedTaskRow])
def get_blocked(request: Request, db: DbSession, user: CurrentUser):
    _auth(request, user)
    return [
        dashboard_service.deadline_row(t)
        for t in dashboard_service.blocked_tasks(db, user)
    ]
