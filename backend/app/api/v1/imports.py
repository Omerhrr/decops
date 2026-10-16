"""Import center endpoints.

Permission model: Company Administrator holds imports.manage + imports.view.
System Administration deliberately does NOT hold imports.view - import
reports carry business content (titles, people), and the policy keeps
technical administration separate from automatic access to confidential content.
Permission failures surface as 404-consistent errors per API conventions.
"""

import json
import uuid

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response

from app.api.deps import CurrentUser, DbSession, require_permission
from app.core.errors import ConflictError, ValidationFailedError
from app.schemas.imports import (
    ImportCommitResult,
    ImportJobOut,
)
from app.services import audit_service, import_service

router = APIRouter(prefix="/imports", tags=["Imports"])


def _auth(request: Request, user: CurrentUser):
    request.state.user = user
    return user


def _parse_json_form(raw: str | None, label: str) -> dict | None:
    if raw is None or raw == "":
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationFailedError(f"{label} must be valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise ValidationFailedError(f"{label} must be a JSON object.")
    return parsed


@router.post("/csv", status_code=201)
def upload_csv(
    request: Request,
    db: DbSession,
    user=Depends(_auth),
    _perm=Depends(require_permission("imports.manage")),
    file: UploadFile = File(...),
    mapping: str | None = Form(default=None),
    options: str | None = Form(default=None),
) -> dict:
    """Upload + validate a legacy CSV; returns the job with validation counts
    ."""
    actor = _auth(request, user)
    mapping_dict = _parse_json_form(mapping, "mapping")
    options_dict = _parse_json_form(options, "options")
    try:
        job = import_service.create_import_job(
            db, actor=actor, upload=file, mapping=mapping_dict, options=options_dict,
        )
    except import_service.ImportError_ as exc:
        raise ConflictError(exc.message, code=exc.code) from exc
    db.commit()
    db.refresh(job)
    return ImportJobOut.from_job(job).model_dump(mode="json")


@router.get("")
def list_imports(
    db: DbSession,
    _perm=Depends(require_permission("imports.view", "imports.manage")),
) -> list[dict]:
    jobs = import_service.list_jobs(db)
    return [ImportJobOut.from_job(j).model_dump(mode="json") for j in jobs]


@router.get("/{job_id}")
def get_import(
    job_id: uuid.UUID,
    db: DbSession,
    _perm=Depends(require_permission("imports.view", "imports.manage")),
) -> dict:
    job = import_service.get_job(db, job_id)
    return ImportJobOut.from_job(job).model_dump(mode="json")


@router.get("/{job_id}/report")
def get_import_report(
    job_id: uuid.UUID,
    db: DbSession,
    _perm=Depends(require_permission("imports.view", "imports.manage")),
) -> dict:
    job = import_service.get_job(db, job_id)
    return import_service.load_report(job)


@router.get("/{job_id}/report/download")
def download_import_report(
    job_id: uuid.UUID,
    db: DbSession,
    _perm=Depends(require_permission("imports.view", "imports.manage")),
) -> Response:
    """Downloadable reconciliation summary."""
    job = import_service.get_job(db, job_id)
    content, filename = import_service.summary_csv(job)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.patch("/{job_id}")
def update_import_config(
    job_id: uuid.UUID,
    payload: dict,
    request: Request,
    db: DbSession,
    user=Depends(_auth),
    _perm=Depends(require_permission("imports.manage")),
) -> dict:
    """Apply a revised column mapping and/or options, then re-validate.

    Body: {"mapping": {header: target|null, ...}, "options": {...}} -
    both keys optional; any provided key triggers re-validation."""
    actor = _auth(request, user)
    job = import_service.get_job(db, job_id)
    mapping = payload.get("mapping")
    options = payload.get("options")
    if mapping is None and options is None:
        raise ValidationFailedError("Provide 'mapping' and/or 'options' to update.")
    if mapping is not None and not isinstance(mapping, dict):
        raise ValidationFailedError("'mapping' must be an object of header -> field.")
    if options is not None and not isinstance(options, dict):
        raise ValidationFailedError("'options' must be an object.")
    try:
        job = import_service.update_job_config(
            db, job, mapping=mapping, options=options,
        )
    except import_service.ImportError_ as exc:
        raise ConflictError(exc.message, code=exc.code) from exc
    audit_service.record_audit_event(
        db, action="import.updated", resource_type="import_job", resource_id=job.id,
        actor=actor, change_summary=f"Import '{job.filename}' mapping/options updated",
    )
    db.commit()
    db.refresh(job)
    return ImportJobOut.from_job(job).model_dump(mode="json")


@router.post("/{job_id}/commit")
def commit_import(
    job_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user=Depends(_auth),
    _perm=Depends(require_permission("imports.manage")),
) -> dict:
    """Commit validated rows in controlled, retry-safe batches
    steps 12-14). Duplicate and failed rows are excluded and reported."""
    actor = _auth(request, user)
    job = import_service.get_job(db, job_id)
    try:
        result = import_service.commit_import(db, actor=actor, job=job)
    except import_service.ImportError_ as exc:
        db.rollback()
        raise ConflictError(exc.message, code=exc.code) from exc
    db.commit()
    return ImportCommitResult(**result).model_dump(mode="json")
