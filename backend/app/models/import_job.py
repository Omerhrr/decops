"""CSV import jobs (spec data_model: import_jobs; Phase 8 CSV Migration).

An import job is a staged, reviewable unit of legacy migration:

1. upload    -> raw CSV stored under the configured import dir; headers
                auto-mapped to DecOps fields (operator may override);
                every row validated, never silently discarded.
2. validated -> row-level report written to `report_storage_key`; counts
                frozen for review; duplicates and ambiguous user names are
                flagged for a human decision (never auto-resolved).
3. committed -> valid rows committed in controlled batches with per-row
                outcomes appended to the report; safe to retry (committed
                rows are recognised by their legacy identifiers and skipped,
                never duplicated).

The job row records the import actor and timestamps (spec rule: "Record the
import actor and timestamp"). The raw report and source file live on disk
under the storage dir; only keys are stored in the database.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin, utcnow
from app.db.types import JSONType, UTCDateTime


class ImportJobStatus(str, enum.Enum):
    draft = "draft"                # uploaded, awaiting (re)validation
    validated = "validated"        # row report ready; commit allowed
    committed = "committed"        # eligible rows committed; terminal
    failed = "failed"              # unrecoverable commit error (retryable)


class ImportJob(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "import_jobs"

    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[ImportJobStatus] = mapped_column(
        String(20), default=ImportJobStatus.draft, nullable=False, index=True
    )

    # Spec counters (reconciliation report headline numbers)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successful_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    warning_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Extra reconciliation detail beyond the spec's four counters
    duplicate_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    already_committed_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    committed_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Storage keys (paths are resolved through the service, never exposed raw)
    source_storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    report_storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Operator-approved column mapping (source column -> DecOps field) and
    # import options (approved initial visibility policy, duplicate matching
    # rules, date format). JSON blobs: schema evolves with the domain module.
    mapping_json: Mapped[dict] = mapped_column(JSONType(), nullable=False, default=dict)
    options_json: Mapped[dict] = mapped_column(JSONType(), nullable=False, default=dict)

    # Task ids created by this job (traceability / reconciliation)
    committed_task_ids: Mapped[list] = mapped_column(JSONType(), nullable=False, default=list)

    file_level_errors: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    uploaded_by = relationship("User", foreign_keys=[uploaded_by_id], lazy="joined")
