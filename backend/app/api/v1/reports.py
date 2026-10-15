"""Reporting & export endpoints (MOD-007, Phase 7; spec api "Dashboards and
Reports" + MOD-005 "Restricted exports").

- GET /reports/task-completion      -> reports.view (Management)
- GET /reports/department-workload  -> reports.view (all departments) OR
                                       reports.department.view (own departments)
- POST /reports/exports             -> exports.approved; CSV download, audited.

Permission failures raise PermissionDeniedError (404, non-enumeration —
consistent with the rest of the API). Every exported row passes the same
access engine as the on-screen register, so exports cannot leak restricted
tasks (exit criterion: "Restricted information does not leak through
reports").
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request, Response

from app.api.deps import CurrentUser, DbSession, require_permission
from app.core.errors import ValidationFailedError
from app.core.context import current_request_id
from app.models import Department
from app.schemas.reports import DepartmentWorkloadReport, ExportRequest, TaskCompletionReport
from app.services import audit_service, report_service
from app.services.task_service import get_user_permission_codes

router = APIRouter(prefix="/reports", tags=["Reports"])


def _auth(request: Request, user: CurrentUser) -> None:
    request.state.user = user


@router.get("/task-completion", response_model=TaskCompletionReport,
            dependencies=[Depends(require_permission("reports.view"))])
def get_task_completion(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    weeks: int = Query(12, ge=1, le=52),
):
    _auth(request, user)
    return report_service.task_completion_report(db, user, weeks=weeks)


@router.get("/department-workload", response_model=DepartmentWorkloadReport,
            dependencies=[Depends(require_permission("reports.view", "reports.department.view"))])
def get_department_workload(
    request: Request,
    db: DbSession,
    user: CurrentUser,
):
    _auth(request, user)
    codes = get_user_permission_codes(db, user)
    management_scope = "reports.view" in codes
    return report_service.department_workload_report(db, user, management_scope=management_scope)


@router.post("/exports", dependencies=[Depends(require_permission("exports.approved"))])
def create_export(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    body: ExportRequest,
):
    _auth(request, user)
    codes = get_user_permission_codes(db, user)

    if body.export_type == "task_register":
        csv_text, rows = report_service.export_task_register(
            db, user,
            status=body.status,
            priority=body.priority,
            department_id=body.department_id,
            q=body.q,
        )
        description = "Task register export"
    elif body.export_type == "department_workload":
        csv_text, rows = report_service.export_department_workload(
            db, user, management_scope="reports.view" in codes
        )
        description = "Department workload export"
    elif body.export_type == "task_completion":
        csv_text, rows = report_service.export_task_completion(db, user, weeks=body.weeks)
        description = "Task completion export"
    else:  # guarded by schema pattern, defensive only
        raise ValidationFailedError("Unknown export type.")

    audit_service.record_audit_event(
        db,
        action="report.exported",
        resource_type="report",
        resource_id=body.export_type,
        actor=user,
        request_id=current_request_id(),
        change_summary=f"{description}: {rows} row(s)",
        metadata={"export_type": body.export_type, "rows": rows},
    )
    db.commit()

    stamp = datetime.now(UTC).strftime("%Y%m%d")
    filename = f"decops_{body.export_type}_{stamp}.csv"
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# Department Workspace data (spec frontend_pages.Department Workspace) lives
# with reports because it reuses the workload aggregation; the department
# itself must exist, and all task content inside is engine-filtered.
@router.get("/departments/{department_id}/workspace")
def get_department_workspace(
    department_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: CurrentUser,
):
    _auth(request, user)
    department = db.get(Department, department_id)
    if department is None:
        from app.core.errors import NotFoundError

        raise NotFoundError("Department not found.")
    return report_service.department_workspace(db, user, department)
