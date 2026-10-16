"""Import API schemas (CSV Migration)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import ImportJobStatus


class ImportOptions(BaseModel):
    """Operator-approved import options."""

    visibility_mode: str = Field(
        default="participants",
        description="Approved initial visibility policy for imported tasks.",
    )
    day_first: bool = Field(
        default=True, description="Interpret ambiguous dd/mm/mm/dd dates day-first."
    )
    match_title_due: bool = Field(
        default=True, description="Duplicate rule: same normalized title + due date."
    )
    match_title_only: bool = Field(
        default=False, description="Duplicate rule: same normalized title (no due date)."
    )
    reuse_task_number: bool = Field(
        default=True,
        description="Reuse a legacy Task ID as task_number when it matches the TSK pattern.",
    )


class ImportMappingUpdate(BaseModel):
    """Header -> target-field overrides; None/'ignore' skips a column."""

    mapping: dict[str, str | None] = Field(default_factory=dict)


class ImportOptionsUpdate(BaseModel):
    options: dict = Field(default_factory=dict)


class ImportJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    status: ImportJobStatus
    total_rows: int
    successful_rows: int
    warning_rows: int
    failed_rows: int
    duplicate_rows: int
    already_committed_rows: int
    committed_rows: int
    created_at: datetime
    completed_at: datetime | None
    uploaded_by_email: str | None = None
    file_level_errors: str | None = None

    @classmethod
    def from_job(cls, job) -> "ImportJobOut":
        return cls(
            id=job.id,
            filename=job.filename,
            status=job.status,
            total_rows=job.total_rows,
            successful_rows=job.successful_rows,
            warning_rows=job.warning_rows,
            failed_rows=job.failed_rows,
            duplicate_rows=job.duplicate_rows,
            already_committed_rows=job.already_committed_rows,
            committed_rows=job.committed_rows,
            created_at=job.created_at,
            completed_at=job.completed_at,
            uploaded_by_email=getattr(getattr(job, "uploaded_by", None), "email", None),
            file_level_errors=job.file_level_errors,
        )


class ImportCommitResult(BaseModel):
    committed_rows: int
    successful_rows: int
    warning_rows: int
    already_committed_rows: int
    task_ids: list[str]
