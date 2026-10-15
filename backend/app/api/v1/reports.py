"""Reporting & export endpoints (MOD-007, Phase 7; spec api "Dashboards and
Reports" + MOD-005 "Restricted exports").

- GET /reports/task-completion -> reports.view (Management)
- GET /reports/department-workload -> reports.view (all departments) OR
                                       reports.department.view (own departments)
- POST /reports/exports -> exports.approved; CSV download, audited.

Permission failures raise PermissionDeniedError (404, non-enumeration -
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
from app.services import audit_service, pdf_service, report_service, settings_service
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
        description = "Task register export"
    elif body.export_type == "department_workload":
        description = "Department workload export"
    elif body.export_type == "task_completion":
        description = "Task completion export"
    else:  # guarded by schema pattern, defensive only
        raise ValidationFailedError("Unknown export type.")

    if body.format == "pdf":
        content, rows = _pdf_export(db, user, body)
    else:
        csv_text, rows = _csv_export(db, user, body, codes)
        content = csv_text.encode("utf-8")

    audit_service.record_audit_event(
        db,
        action="report.exported",
        resource_type="report",
        resource_id=body.export_type,
        actor=user,
        request_id=current_request_id(),
        change_summary=f"{description}: {rows} row(s), {body.format}",
        metadata={"export_type": body.export_type, "rows": rows, "format": body.format},
    )
    db.commit()

    stamp = datetime.now(UTC).strftime("%Y%m%d")
    extension = "pdf" if body.format == "pdf" else "csv"
    media = "application/pdf" if body.format == "pdf" else "text/csv; charset=utf-8"
    filename = f"decops_{body.export_type}_{stamp}.{extension}"
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _csv_export(db, user, body: ExportRequest, codes: set[str]) -> tuple[str, int]:
    if body.export_type == "task_register":
        return report_service.export_task_register(
            db, user,
            status=body.status,
            priority=body.priority,
            department_id=body.department_id,
            q=body.q,
        )
    if body.export_type == "department_workload":
        return report_service.export_department_workload(
            db, user, management_scope="reports.view" in codes
        )
    return report_service.export_task_completion(db, user, weeks=body.weeks)


def _pdf_export(db, user, body: ExportRequest) -> tuple[bytes, int]:
    org = settings_service.get_org_settings(db)
    design = settings_service.get_pdf_design(db)
    if body.export_type == "task_register":
        visible = report_service.filter_visible_tasks(
            db, user,
            status=body.status,
            priority=body.priority,
            department_id=body.department_id,
            q=body.q,
        )
        rows = [report_service.task_register_row(t) for t in visible]
        content = pdf_service.task_register_pdf(
            db, user, org, design, rows=rows, row_count=len(rows)
        )
        return content, len(rows)
    if body.export_type == "department_workload":
        codes = get_user_permission_codes(db, user)
        report = report_service.department_workload_report(
            db, user, management_scope="reports.view" in codes
        )
        content = pdf_service.department_workload_pdf(db, user, org, design, report)
        return content, len(report["departments"])
    report = report_service.task_completion_report(db, user, weeks=body.weeks)
    content = pdf_service.task_completion_pdf(db, user, org, design, report)
    return content, len(report["series"])


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
