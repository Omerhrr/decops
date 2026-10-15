"""CSV import orchestration (Phase 8, spec spreadsheet_migration pipeline).

Pipeline: upload -> validate/mapping -> preview/report -> commit (batched,
retry-safe) -> reconciliation summary.

Safety properties (spec rules):
- invalid rows are NEVER silently discarded (row report lists everything);
- ambiguous users are flagged, never invented (domain module resolution);
- imports cannot grant unauthorized access: tasks are created with the
  operator-approved initial visibility policy and no extra grants beyond the
  accountable/supporting PM assignments (which are inherent participants);
- legacy attachment links are stored verbatim as untrusted references and
  never fetched;
- no historical audit events are fabricated: activity rows record the import
  actor and provenance ("imported from legacy spreadsheet ..."), and audit
  events record the import as what it is;
- commits are retry-safe: already-committed legacy identifiers are recognised
  and skipped, never duplicated.
"""

import csv
import io
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.domain import csv_import as ci
from app.models import (
    AssignmentRoleType,
    ImportJob,
    ImportJobStatus,
    Task,
    TaskAssignment,
    User,
)
from app.models.task import ProgressMode, TaskPriority, TaskStatus
from app.services import audit_service

TASK_NUMBER_RE = re.compile(r"^TSK-\d{4}-\d{4,6}$", re.I)
CSV_EXTENSION = ".csv"


class ImportError_(Exception):
    def __init__(self, message: str, *, code: str = "import_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

def _job_dir(job_id: uuid.UUID) -> Path:
    base = Path(get_settings().import_storage_dir)
    path = base / str(job_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _source_path(job: ImportJob) -> Path:
    if not job.source_storage_key:
        raise NotFoundError("Import source file is missing.")
    return Path(get_settings().import_storage_dir) / job.source_storage_key


def _report_path(job: ImportJob) -> Path:
    if not job.report_storage_key:
        raise NotFoundError("Import report is missing.")
    return Path(get_settings().import_storage_dir) / job.report_storage_key


DEFAULT_OPTIONS: dict = {
    # Approved initial visibility policy for imported tasks (spec
    # legacy_data_policy.legacy_access: "explicitly approved").
    "visibility_mode": "participants",
    # Ambiguous dd/mm vs mm/dd interpretation for legacy dates.
    "day_first": True,
    # Duplicate matching rules (configurable per spec pipeline step 9).
    "match_title_due": True,
    "match_title_only": False,
    # Reuse a legacy "Task ID" as the DecOps task_number when it already
    # matches the TSK-YYYY-NNNN pattern and is unallocated.
    "reuse_task_number": True,
}

VALID_VISIBILITY_MODES = {"private", "participants", "department_scoped", "custom"}


def _clean_options(raw: dict | None) -> dict:
    options = dict(DEFAULT_OPTIONS)
    for key, value in (raw or {}).items():
        if key in options:
            options[key] = value
    if options["visibility_mode"] not in VALID_VISIBILITY_MODES:
        raise ValidationFailedError(
            f"visibility_mode must be one of {sorted(VALID_VISIBILITY_MODES)}."
        )
    options["day_first"] = bool(options["day_first"])
    options["match_title_due"] = bool(options["match_title_due"])
    options["match_title_only"] = bool(options["match_title_only"])
    options["reuse_task_number"] = bool(options["reuse_task_number"])
    return options


def _clean_mapping(raw: dict | None, headers: list[str]) -> dict[str, str | None]:
    """Merge an operator-supplied mapping over the auto-mapping (spec pipeline
    step 3: authorized users map source columns to DecOps fields)."""
    mapping = ci.auto_map_headers(headers)
    for header, target in (raw or {}).items():
        if header not in mapping:
            raise ValidationFailedError(
                f"Column '{header}' is not present in the uploaded file."
            )
        if target in (None, "", "ignore"):
            mapping[header] = None
        elif target in ci.TARGET_FIELDS:
            # one target per import
            for h, t in list(mapping.items()):
                if h != header and t == target:
                    mapping[h] = None
            mapping[header] = target
        else:
            raise ValidationFailedError(
                f"Column '{header}' cannot map to unknown field '{target}'."
            )
    return mapping


# ---------------------------------------------------------------------------
# Directory / duplicate snapshots
# ---------------------------------------------------------------------------

def _build_directory(db: Session) -> ci.UserDirectory:
    users = db.scalars(select(User)).all()
    return ci.UserDirectory(users=[
        ci.DirectoryUser(
            user_id=str(u.id),
            full_name=u.full_name,
            email=u.email,
            employee_code=u.employee_code,
            is_active=_is_active(u),
        )
        for u in users
    ])


def _is_active(user: User) -> bool:
    status = user.account_status
    value = status.value if hasattr(status, "value") else str(status)
    return value == "active"


def _build_duplicate_index(db: Session, options: dict) -> ci.DuplicateIndex:
    rows = db.execute(
        select(Task.id, Task.task_number, Task.title, Task.due_date, Task.legacy_external_id)
    ).all()
    refs = [
        ci.ExistingTaskRef(
            task_id=str(r.id),
            task_number=r.task_number,
            title=r.title,
            due_date=r.due_date.isoformat() if r.due_date else None,
            legacy_external_id=r.legacy_external_id,
        )
        for r in rows
    ]
    return ci.DuplicateIndex(
        refs,
        match_title_due=options["match_title_due"],
        match_title_only=options["match_title_only"],
    )


# ---------------------------------------------------------------------------
# Parse + validate
# ---------------------------------------------------------------------------

def _read_upload(upload: UploadFile) -> str:
    cfg = get_settings()
    filename = Path(upload.filename or "").name.strip()
    if not filename.lower().endswith(CSV_EXTENSION):
        raise ValidationFailedError("Only .csv files can be imported.")
    upload.file.seek(0, io.SEEK_END)
    size = upload.file.tell()
    upload.file.seek(0)
    if size == 0:
        raise ValidationFailedError("The uploaded file is empty.")
    if size > cfg.import_max_bytes:
        raise ValidationFailedError(
            f"The file exceeds the {cfg.import_max_bytes // (1024 * 1024)} MB import limit."
        )
    raw = upload.file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationFailedError(
            "The file must be UTF-8 encoded (with or without BOM); "
            "re-export the spreadsheet as UTF-8 CSV.",
        ) from exc
    if "\x00" in text:
        raise ValidationFailedError("The file looks binary, not a text CSV.")
    return text


def _parse_csv(text: str) -> tuple[list[str], list[dict[str, str]]]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    try:
        headers = [h.strip() for h in (reader.fieldnames or [])]
    except UnicodeDecodeError:
        headers = list(reader.fieldnames or [])
    if not headers:
        raise ValidationFailedError("No header row found in the CSV.")
    # Rebuild with cleaned headers so row lookups are stable.
    normalized_rows: list[dict[str, str]] = []
    for raw_row in reader:
        row = {}
        for key, value in (raw_row or {}).items():
            if key is None:
                # extra unnamed columns -> fold into an ignored key
                continue
            row[key.strip()] = (value or "").strip() if isinstance(value, str) else ""
        normalized_rows.append(row)
    return headers, normalized_rows


def _write_report(job: ImportJob, payload: dict) -> None:
    path = _job_dir(job.id) / "report.json"
    path.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    job.report_storage_key = f"{job.id}/report.json"


def validate_job(db: Session, job: ImportJob) -> ImportJob:
    """(Re)validate the stored source file with the current mapping/options
    and (re)write the row-level validation report (spec pipeline steps 4-10)."""
    if job.status == ImportJobStatus.committed:
        raise ConflictError("This import was already committed and can no longer change.",
                            code="import_committed")
    text = _source_path(job).read_text(encoding="utf-8-sig")
    headers, rows = _parse_csv(text)
    mapping = _clean_mapping(job.mapping_json, headers)
    job.mapping_json = mapping
    options = _clean_options(job.options_json)
    job.options_json = options

    directory = _build_directory(db)
    duplicate_index = _build_duplicate_index(db, options)

    reports: list[ci.RowReport] = []
    for index, row in enumerate(rows, start=2):  # header is row 1
        reports.append(ci.validate_row(
            row,
            row_number=index,
            mapping=mapping,
            directory=directory,
            duplicates=duplicate_index,
            day_first=options["day_first"],
        ))

    # Intra-file duplicate pass: the DB index cannot see rows of THIS file,
    # so flag exact legacy-id repeats (would double-import) and likely
    # repeats (same normalized title + due date) within the file itself.
    seen_exact: dict[str, int] = {}
    seen_soft: dict[tuple[str, str], int] = {}
    for report in reports:
        if report.status == ci.ROW_FAILED:
            continue
        legacy = (report.source_task_id or "").strip().upper()
        if legacy:
            first_row = seen_exact.get(legacy)
            if first_row:
                report.status = ci.ROW_FAILED
                report.normalized = None
                report.errors.append(
                    f"Duplicate within file: Task ID {legacy} already appears at row {first_row}."
                )
                report.duplicates.append({
                    "kind": "exact_in_file", "task_number": f"row {first_row}",
                    "title": "", "reason": f"Task ID {legacy} repeats at row {first_row}.",
                })
                continue
            seen_exact[legacy] = report.row_number
        if report.normalized:
            due = report.normalized.due_date or ""
            soft_key = (report.normalized.title.strip().lower(), due)
            if due:
                first_row = seen_soft.get(soft_key)
                if first_row and first_row != report.row_number:
                    report.normalized.duplicate_review = True
                    report.notices.append(
                        f"Likely duplicate within file: same title and due date as row {first_row}; "
                        "excluded from commit unless revalidated."
                    )
                    report.duplicates.append({
                        "kind": "likely_in_file", "task_number": f"row {first_row}",
                        "title": report.normalized.title,
                        "reason": f"Same title and due date as row {first_row} of this file.",
                    })
                    if report.status == ci.ROW_OK:
                        report.status = ci.ROW_WARNING
                    continue
                seen_soft[soft_key] = report.row_number

    counts = ci.count_rows(reports)
    job.total_rows = counts["total"]
    job.successful_rows = counts["successful"]
    job.warning_rows = counts["warning"]
    job.failed_rows = counts["failed"]
    job.duplicate_rows = sum(1 for r in reports if r.duplicates)
    mapped_targets = {t for t in mapping.values() if t}
    missing_required = [f for f in ("title", "accountable_pm") if f not in mapped_targets]
    file_errors: list[str] = []
    for field_name in missing_required:
        file_errors.append(f"No source column is mapped to required field '{field_name}'.")
    if not rows:
        file_errors.append("The file contains no data rows.")
    job.file_level_errors = "\n".join(file_errors) or None
    job.status = ImportJobStatus.validated

    _write_report(job, {
        "job_id": str(job.id),
        "filename": job.filename,
        "headers": headers,
        "mapping": mapping,
        "options": options,
        "unmapped_headers": [h for h, t in mapping.items() if t is None],
        "file_level_errors": file_errors,
        "counts": counts,
        "generated_at": datetime.now(UTC).isoformat(),
        "rows": [r.to_dict() for r in reports],
    })
    db.flush()
    return job


def create_import_job(
    db: Session,
    *,
    actor: User,
    upload: UploadFile,
    mapping: dict | None = None,
    options: dict | None = None,
) -> ImportJob:
    """Spec pipeline step 1-2: upload + validate file type/size/encoding/headers."""
    text = _read_upload(upload)  # file-level problems reject WITHOUT a job row
    filename = Path(upload.filename or "").name.strip()

    job = ImportJob(
        uploaded_by_id=actor.id,
        filename=filename,
        status=ImportJobStatus.draft,
        mapping_json=mapping or {},
        options_json=options or {},
    )
    db.add(job)
    db.flush()  # allocate the id for storage paths

    source_rel = f"{job.id}/source.csv"
    (_job_dir(job.id) / "source.csv").write_text(text, encoding="utf-8")
    job.source_storage_key = source_rel

    try:
        validate_job(db, job)
    except Exception:
        # Header-structure failures reject the upload cleanly (no phantom job).
        db.rollback()
        import shutil

        shutil.rmtree(_job_dir(job.id), ignore_errors=True)
        raise
    audit_service.record_audit_event(
        db, action="import.created", resource_type="import_job", resource_id=job.id,
        actor=actor, change_summary=f"CSV import '{filename}' uploaded and validated",
        metadata={"filename": filename, "total_rows": job.total_rows},
    )
    return job


def update_job_config(db: Session, job: ImportJob, *, mapping: dict | None,
                      options: dict | None) -> ImportJob:
    """Apply an operator-approved mapping/options update and re-validate."""
    if job.status == ImportJobStatus.committed:
        raise ConflictError("This import was already committed.", code="import_committed")
    if mapping is not None:
        job.mapping_json = mapping
    if options is not None:
        job.options_json = options
    validate_job(db, job)
    return job


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def get_job(db: Session, job_id: uuid.UUID) -> ImportJob:
    job = db.get(ImportJob, job_id)
    if job is None:
        raise NotFoundError("Import job not found.")
    return job


def list_jobs(db: Session, *, limit: int = 100) -> list[ImportJob]:
    stmt = (
        select(ImportJob)
        .order_by(ImportJob.created_at.desc())
        .limit(min(limit, 200))
    )
    return list(db.scalars(stmt).all())


def load_report(job: ImportJob) -> dict:
    path = _report_path(job)
    if not path.exists():
        raise NotFoundError("Import report not found.")
    return json.loads(path.read_text(encoding="utf-8"))


def summary_csv(job: ImportJob) -> tuple[str, str]:
    """Reconciliation summary download (spec pipeline step 15)."""
    report = load_report(job)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "Row", "Source Task ID", "Task Title", "Validation", "Outcome",
        "DecOps Task Number", "Errors", "Notices", "Duplicates",
    ])
    for row in report.get("rows", []):
        writer.writerow([
            row.get("row_number"),
            row.get("source_task_id") or "",
            row.get("title") or "",
            row.get("status") or "",
            row.get("outcome") or "",
            row.get("committed_task_number") or "",
            " | ".join(row.get("errors") or []),
            " | ".join(row.get("notices") or []),
            " | ".join(
                f"{d.get('kind')}:{d.get('task_number')}" for d in (row.get("duplicates") or [])
            ),
        ])
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(job.filename).stem) or "import"
    return buffer.getvalue(), f"import-summary-{base}-{stamp}.csv"


# ---------------------------------------------------------------------------
# Commit (spec pipeline steps 12-14)
# ---------------------------------------------------------------------------

def _noon(date_iso: str | None) -> datetime | None:
    if not date_iso:
        return None
    d = datetime.fromisoformat(date_iso).date()
    return datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=UTC)


def _next_task_number(db: Session) -> str:
    year = datetime.now(UTC).year
    prefix = f"TSK-{year}-"
    count = int(db.scalar(
        select(func.count(Task.id)).where(Task.task_number.like(f"{prefix}%"))
    ) or 0)
    for candidate in range(count + 1, count + 1000):
        number = f"{prefix}{candidate:04d}"
        exists = db.scalar(select(Task.id).where(Task.task_number == number)) is not None
        if not exists:
            return number
    raise ImportError_("Unable to allocate a task number.", code="number_exhausted")


def _legacy_taken(db: Session, legacy_id: str) -> bool:
    """True when a task already exists for this legacy identifier (from this
    job or any earlier import) — retry safety without duplicates."""
    if not legacy_id:
        return False
    stmt = select(Task.id).where(
        (func.upper(Task.task_number) == legacy_id.upper())
        | (func.upper(Task.legacy_external_id) == legacy_id.upper())
    )
    return db.scalar(stmt.limit(1)) is not None


def commit_import(
    db: Session,
    *,
    actor: User,
    job: ImportJob,
    batch_size: int = 100,
) -> dict:
    """Commit committable rows in controlled batches (spec pipeline step 12).

    Committable = validated ok/warning rows that are not flagged for duplicate
    review. Failed rows and duplicates are reported, never committed. Safe to
    retry: legacy identifiers already present in DecOps are skipped and
    reported as already_committed (spec rule: "Support safe retries without
    duplicating previously committed records").
    """
    if job.status == ImportJobStatus.committed:
        raise ConflictError("This import was already committed.", code="import_committed")
    if job.status != ImportJobStatus.validated:
        raise ConflictError("Validate the import before committing.", code="import_not_validated")

    report = load_report(job)
    rows: list[dict] = report.get("rows", [])
    options = _clean_options(job.options_json)

    eligible_numbers = {
        r["row_number"] for r in rows
        if r.get("status") != ci.ROW_FAILED
        and r.get("normalized")
        and not (r.get("normalized") or {}).get("duplicate_review")
    }
    if not eligible_numbers:
        raise ConflictError(
            "No committable rows: every row failed validation or needs review.",
            code="nothing_to_commit",
        )

    # Cumulative across retry runs: whatever previous runs committed stays.
    committed_task_ids: list[str] = list(job.committed_task_ids or [])
    run_seen_legacy: set[str] = set()
    outcome_updates: dict[int, dict] = {}

    ok_committed = 0
    warn_committed = 0
    already_committed = 0
    failed_at_commit: list[str] = []
    pending_ids: list[str] = []

    def _persist_batch() -> None:
        """Make the batch durable together with the job counters (retry safety)."""
        nonlocal pending_ids
        try:
            job.committed_task_ids = committed_task_ids + pending_ids
            job.committed_rows = len(job.committed_task_ids)
            db.commit()
        except Exception as exc:
            db.rollback()
            raise ImportError_(
                f"Batch commit failed: {exc}", code="batch_commit_failed"
            ) from exc
        committed_task_ids.extend(pending_ids)
        pending_ids = []

    for row in rows:
        if row["row_number"] not in eligible_numbers:
            continue
        normalized = row["normalized"]
        legacy_id = (normalized.get("legacy_task_id") or "").strip() or None

        # Fresh duplicate check at commit time (state may have changed since
        # validation) — exact identifiers only.
        if legacy_id and (legacy_id.upper() in run_seen_legacy or _legacy_taken(db, legacy_id)):
            already_committed += 1
            outcome_updates[row["row_number"]] = {
                "outcome": "already_committed",
            }
            continue

        normalized["_row_number"] = row["row_number"]
        try:
            task = _create_task_from_row(
                db, actor=actor, job=job, normalized=normalized, options=options,
            )
        except Exception as exc:  # row-level commit failure aborts the run
            db.rollback()
            failed_at_commit.append(
                f"Row {row['row_number']}: {type(exc).__name__}: {exc}"
            )
            raise ImportError_(
                f"Commit aborted at row {row['row_number']}: {exc}; "
                "previously committed rows are kept (safe to retry).",
                code="commit_row_failed",
            ) from exc

        if legacy_id:
            run_seen_legacy.add(legacy_id.upper())
        if row.get("status") == ci.ROW_WARNING:
            warn_committed += 1
        else:
            ok_committed += 1
        outcome_updates[row["row_number"]] = {
            "outcome": "committed",
            "committed_task_id": str(task.id),
            "committed_task_number": task.task_number,
        }
        pending_ids.append(str(task.id))
        if len(pending_ids) >= max(1, batch_size):
            _persist_batch()

    if pending_ids:
        _persist_batch()

    # Final job state + regenerated report with per-row outcomes
    job.successful_rows = ok_committed
    job.warning_rows = warn_committed
    job.already_committed_rows = already_committed
    job.committed_rows = len(committed_task_ids)
    job.committed_task_ids = list(committed_task_ids)
    job.status = ImportJobStatus.committed
    job.completed_at = datetime.now(UTC)

    for row in rows:
        update = outcome_updates.get(row["row_number"])
        if update:
            row.update(update)
    report["commit"] = {
        "committed_by": actor.email,
        "committed_at": job.completed_at.isoformat(),
        "committed_rows": job.committed_rows,
        "already_committed_rows": already_committed,
        "task_ids": list(committed_task_ids),
        "errors": failed_at_commit,
    }
    report["counts"]["committed"] = job.committed_rows
    report["counts"]["already_committed"] = already_committed
    _write_report(job, report)

    db.flush()
    audit_service.record_audit_event(
        db, action="import.committed", resource_type="import_job", resource_id=job.id,
        actor=actor,
        change_summary=(
            f"CSV import '{job.filename}' committed {job.committed_rows} tasks "
            f"({already_committed} already committed)"
        ),
        metadata={
            "filename": job.filename,
            "total_rows": job.total_rows,
            "committed_rows": job.committed_rows,
            "task_ids_sample": committed_task_ids[:10],
        },
    )
    return {
        "committed_rows": job.committed_rows,
        "successful_rows": ok_committed,
        "warning_rows": warn_committed,
        "already_committed_rows": already_committed,
        "task_ids": committed_task_ids,
    }


def _create_task_from_row(
    db: Session, *, actor: User, job: ImportJob, normalized: dict, options: dict,
) -> Task:
    """Create one historical task (spec legacy_data_policy).

    Historical timestamps are preserved when provided and reliable; status
    comes from the approved mapping; the initial visibility policy is the
    operator-approved import option; the import actor records provenance —
    historical audit events are NOT fabricated.
    """
    legacy_id = (normalized.get("legacy_task_id") or "").strip() or None

    task_number: str | None = None
    if legacy_id and options["reuse_task_number"] and TASK_NUMBER_RE.match(legacy_id):
        if not _legacy_taken(db, legacy_id):
            task_number = legacy_id.upper()
    if task_number is None:
        task_number = _next_task_number(db)

    status_value = normalized.get("status") or "open"
    completed_at = _noon(normalized.get("completion_date")) if status_value == "completed" else None

    def _as_date(key: str):
        value = normalized.get(key)
        return datetime.fromisoformat(value).date() if value else None

    task = Task(
        task_number=task_number,
        title=normalized["title"],
        description=normalized.get("description") or None,
        priority=TaskPriority(normalized.get("priority") or "medium"),
        status=TaskStatus(status_value),
        accountable_pm_id=uuid.UUID(normalized["accountable_pm_id"]),
        created_by_id=actor.id,
        start_date=_as_date("start_date"),
        due_date=_as_date("due_date"),
        next_follow_up_date=_as_date("next_follow_up_date"),
        percent_complete=int(normalized.get("percent_complete") or 0),
        progress_mode=ProgressMode.manual,
        dependency_summary=normalized.get("dependency_summary"),
        attachment_folder_reference=normalized.get("attachment_folder_reference"),
        legacy_external_id=legacy_id if task_number != (legacy_id or "").upper() else None,
        visibility_mode=options["visibility_mode"],
        completed_at=completed_at,
        # Historical creation timestamp preserved when provided (noon UTC).
        created_at=_noon(normalized.get("date_created")) or datetime.now(UTC),
        version=1,
    )
    db.add(task)
    db.flush()

    assigned_by_id = uuid.UUID(normalized["assigned_by_id"]) if normalized.get("assigned_by_id") else actor.id
    db.add(TaskAssignment(
        task_id=task.id,
        user_id=task.accountable_pm_id,
        assignment_role=AssignmentRoleType.accountable_pm,
        assigned_by_id=assigned_by_id,
    ))
    for pm_id in normalized.get("supporting_pm_ids") or []:
        db.add(TaskAssignment(
            task_id=task.id,
            user_id=uuid.UUID(pm_id),
            assignment_role=AssignmentRoleType.supporting_pm,
            assigned_by_id=actor.id,
        ))

    source_ref = f", source ID {legacy_id}" if legacy_id else ""
    row_number = normalized.get("_row_number")
    row_note = f", row {row_number}" if row_number else ""
    db.add(
        _activity(
            task_id=task.id,
            actor_id=actor.id,
            summary=(
                f"Imported from legacy spreadsheet '{job.filename}'{row_note}{source_ref}"
            ),
            detail={
                "import_job_id": str(job.id),
                "legacy_task_id": legacy_id,
                "percent_requires_reconciliation": bool(
                    normalized.get("percent_requires_reconciliation")
                ),
            },
        )
    )
    audit_service.record_audit_event(
        db, action="task.created", resource_type="task", resource_id=task.id,
        actor=actor,
        change_summary=f"Imported task '{task.title}' ({task.task_number}) from '{job.filename}'",
        metadata={
            "imported": True,
            "import_job_id": str(job.id),
            "legacy_task_id": legacy_id,
            "task_number": task.task_number,
            "visibility_mode": options["visibility_mode"],
        },
    )
    return task


def _activity(*, task_id, actor_id, summary: str, detail: dict):
    from app.models import TaskActivity

    return TaskActivity(
        task_id=task_id,
        actor_id=actor_id,
        activity_type="task.imported",
        summary=summary[:500],
        detail=detail,
    )
