"""CSV migration domain logic (Phase 8, spec spreadsheet_migration).

Pure functions and value objects only: no database, no framework imports.
The service layer feeds directory snapshots / existing-task indexes in and
persists the row reports this module produces.

Spec rules implemented here:
- approved mapping tables for legacy statuses and priorities; unmapped values
  are REPORTED, never invented or silently defaulted into wrong data;
- ambiguous employee names are flagged for manual resolution — a mapping is
  never invented;
- required fields and date relationships are validated per row;
- whitespace is normalized everywhere; dates accept a configurable day-first
  vs month-first interpretation (legacy spreadsheets are ambiguous);
- legacy dependency descriptions and attachment links are preserved verbatim
  (untrusted references are stored, never fetched or resolved automatically);
- duplicate detection uses legacy identifiers plus configurable matching rules
  (exact task_number, exact legacy id, title+due-date, title-only).
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime

# ---------------------------------------------------------------------------
# Source schema (spec spreadsheet_migration.source_columns)
# ---------------------------------------------------------------------------

SOURCE_COLUMNS: tuple[str, ...] = (
    "Task ID",
    "Date Created",
    "Task Title",
    "Task Description",
    "Priority",
    "Accountable PM",
    "Supporting PM(s)",
    "Assigned By",
    "Start Date",
    "Due Date",
    "Status",
    "% Complete",
    "Last Updated",
    "Next Follow-up Date",
    "Dependency / Blocker",
    "Attachment / Folder Link",
    "Completion Date",
)

TARGET_FIELDS: tuple[str, ...] = (
    "legacy_task_id",       # Task ID -> task_number when reusable, else legacy_external_id
    "date_created",
    "title",
    "description",
    "priority",
    "accountable_pm",
    "supporting_pms",
    "assigned_by",
    "start_date",
    "due_date",
    "status",
    "percent_complete",
    "last_updated",
    "next_follow_up_date",
    "dependency_summary",
    "attachment_folder_reference",
    "completion_date",
)

# Source column -> default target field (spec spreadsheet_migration.mapping)
DEFAULT_COLUMN_MAPPING: dict[str, str | None] = {
    "Task ID": "legacy_task_id",
    "Date Created": "date_created",
    "Task Title": "title",
    "Task Description": "description",
    "Priority": "priority",
    "Accountable PM": "accountable_pm",
    "Supporting PM(s)": "supporting_pms",
    "Assigned By": "assigned_by",
    "Start Date": "start_date",
    "Due Date": "due_date",
    "Status": "status",
    "% Complete": "percent_complete",
    "Last Updated": "last_updated",
    "Next Follow-up Date": "next_follow_up_date",
    "Dependency / Blocker": "dependency_summary",
    "Attachment / Folder Link": "attachment_folder_reference",
    "Completion Date": "completion_date",
}

# Targets that must resolve to a DecOps date/datetime field
DATE_TARGETS = frozenset({
    "date_created", "start_date", "due_date", "next_follow_up_date",
    "last_updated", "completion_date",
})


def auto_map_headers(headers: list[str]) -> dict[str, str | None]:
    """Map spreadsheet headers to DecOps fields (spec pipeline step 3).

    Matching is normalization-based (case, punctuation, whitespace) with a
    curated alias list; unmapped headers yield None so the operator can map
    them explicitly or leave them ignored (reported, never dropped silently).
    """
    def norm(value: str) -> str:
        return re.sub(r"[^a-z0-9]", "", (value or "").lower())

    aliases: dict[str, str | None] = {}
    for column, target in DEFAULT_COLUMN_MAPPING.items():
        aliases[norm(column)] = target
    # Extra aliases commonly found in Interdec exports
    aliases.update({
        norm("Task Name"): "title",
        norm("Subject"): "title",
        norm("Percent Complete"): "percent_complete",
        norm("Progress"): "percent_complete",
        norm("PM Accountable"): "accountable_pm",
        norm("Owner"): "accountable_pm",
        norm("Follow Up Date"): "next_follow_up_date",
        norm("Blocker"): "dependency_summary",
        norm("Dependencies"): "dependency_summary",
        norm("Notes"): "description",
        norm("Comments"): "description",
        norm("Created"): "date_created",
        norm("Updated"): "last_updated",
        norm("Closed Date"): "completion_date",
        norm("Finished Date"): "completion_date",
    })

    mapping: dict[str, str | None] = {}
    used_targets: set[str] = set()
    for header in headers:
        if header in mapping:
            # Repeated header key: DictReader collapses duplicates to one
            # column, so the first mapping stands.
            continue
        target = aliases.get(norm(header))
        # One target per import: first header wins, duplicates map to None
        if target and target in used_targets:
            target = None
        if target:
            used_targets.add(target)
        mapping[header] = target
    return mapping


# ---------------------------------------------------------------------------
# Approved mapping tables (spec legacy_data_policy.legacy_statuses + rules)
# ---------------------------------------------------------------------------

STATUS_MAPPING: dict[str, str] = {
    # draft
    "draft": "draft", "new": "draft", "template": "draft",
    # open
    "open": "open", "not started": "open", "notstarted": "open",
    "pending": "open", "to do": "open", "todo": "open", "backlog": "open",
    "queued": "open", "assigned": "open",
    # in_progress
    "in progress": "in_progress", "in_progress": "in_progress",
    "inprogress": "in_progress", "started": "in_progress",
    "active": "in_progress", "ongoing": "in_progress",
    "wip": "in_progress", "working": "in_progress",
    # blocked
    "blocked": "blocked", "on hold": "blocked", "onhold": "blocked",
    "waiting": "blocked", "impeded": "blocked", "stalled": "blocked",
    # under_review
    "under review": "under_review", "under_review": "under_review",
    "in review": "under_review", "review": "under_review",
    "submitted for review": "under_review", "awaiting approval": "under_review",
    # completed
    "completed": "completed", "complete": "completed", "done": "completed",
    "closed": "completed", "finished": "completed", "delivered": "completed",
    # cancelled
    "cancelled": "cancelled", "canceled": "cancelled", "abandoned": "cancelled",
    "rejected": "cancelled", "void": "cancelled",
    # archived
    "archived": "archived", "archive": "archived",
}

PRIORITY_MAPPING: dict[str, str] = {
    "critical": "critical", "p0": "critical", "urgent": "critical",
    "asap": "critical", "emergency": "critical", "highest": "critical",
    "high": "high", "p1": "high", "important": "high",
    "medium": "medium", "med": "medium", "normal": "medium",
    "p2": "medium", "moderate": "medium", "m": "medium",
    "low": "low", "p3": "low", "minor": "low", "lowest": "low",
    "trivial": "low",
}

PRIORITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class RowError(Exception):
    """A row-level validation failure carrying a human-readable reason."""


def normalize_status(raw: str | None) -> str:
    """Apply the approved status mapping table; unmapped values are errors."""
    text = (raw or "").strip().lower().replace("_", " ").strip()
    if not text:
        # Empty status is a normalizable default (new legacy work starts open),
        # recorded as a notice by the row validator via STATUS_EMPTY sentinel.
        return "open"
    if text in STATUS_MAPPING:
        return STATUS_MAPPING[text]
    raise RowError(f"Unmapped legacy status '{raw.strip()}' (approved mapping table has no entry).")


def normalize_priority(raw: str | None) -> tuple[str, bool]:
    """Returns (priority, defaulted). Unmapped non-empty values are errors."""
    text = (raw or "").strip().lower().strip()
    if not text:
        return "medium", True
    if text in PRIORITY_MAPPING:
        return PRIORITY_MAPPING[text], False
    raise RowError(f"Unmapped legacy priority '{raw.strip()}'.")


def normalize_percent(raw: str | None) -> tuple[int, bool]:
    """Returns (percent 0-100, reconcilable).

    Spec legacy_data_policy.historical_progress: import the supplied
    percentage but flag records requiring reconciliation with the new
    workflow calculation -> any supplied percentage is marked reconcilable.
    """
    text = (raw or "").strip().replace("%", "").strip()
    if not text:
        return 0, False
    try:
        value = float(text)
    except ValueError as exc:
        raise RowError(f"'{raw.strip()}' is not a valid percentage.") from exc
    if value < 0 or value > 100:
        raise RowError(f"Percentage {value:g} is outside 0-100.")
    if 0 < value < 1 and "." in text:
        value = value * 100  # 0.35 -> 35 (fraction style)
    percent = round(value)
    return percent, percent > 0


_DATE_FORMATS = (
    "%Y-%m-%d",       # ISO
    "%Y/%m/%d",
    "%d/%m/%Y",       # legacy day-first
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%m/%d/%Y",       # month-first
    "%d %b %Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%B %d, %Y",
)


def parse_date(raw: str | None, *, day_first: bool = True) -> date:
    """Parse a legacy date. Unparseable non-empty values are errors.

    `day_first` selects how ambiguous dd/mm vs mm/dd input is read
    (spec: dates normalized via an explicit, operator-approved format).
    """
    text = (raw or "").strip()
    if not text:
        raise RowError("Date is empty.")  # only called where a date is required
    text = re.sub(r"\s+", " ", text)
    candidates = list(_DATE_FORMATS)
    if day_first:
        # Try day-first variants before month-first ones.
        candidates.sort(key=lambda fmt: 0 if "%d/%m" in fmt or "%d-%m" in fmt or "%d.%m" in fmt else 1)
    else:
        candidates.sort(key=lambda fmt: 0 if "%m/%d" in fmt else 1)
    for fmt in candidates:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise RowError(f"'{text}' is not a recognized date (expected e.g. 2025-03-14 or 14/03/2025).")


def parse_optional_date(raw: str | None, *, day_first: bool = True) -> date | None:
    text = (raw or "").strip()
    if not text:
        return None
    return parse_date(text, day_first=day_first)


def parse_datetime_value(raw: str | None, *, day_first: bool = True) -> datetime | None:
    """Historical timestamps preserved when reliable (spec legacy policy)."""
    parsed = parse_optional_date(raw, day_first=day_first)
    return datetime(parsed.year, parsed.month, parsed.day, 12, 0, 0) if parsed else None


def split_people(raw: str | None) -> list[str]:
    """Split a people cell ('Ann; Bob, Chen') into clean individual names."""
    text = (raw or "").strip()
    if not text:
        return []
    if ";" in text:
        parts = text.split(";")
    else:
        parts = text.split(",")
    return [re.sub(r"\s+", " ", p).strip(" .") for p in parts if p.strip(" .")]


# ---------------------------------------------------------------------------
# User resolution (spec: resolve names against the user directory; never
# invent a mapping when names are ambiguous)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DirectoryUser:
    user_id: str
    full_name: str
    email: str
    employee_code: str
    is_active: bool


@dataclass
class UserDirectory:
    users: list[DirectoryUser]
    _by_email: dict[str, list[DirectoryUser]] = field(default_factory=dict, init=False)
    _by_code: dict[str, list[DirectoryUser]] = field(default_factory=dict, init=False)
    _by_name: dict[str, list[DirectoryUser]] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        for user in self.users:
            self._by_email.setdefault(user.email.strip().lower(), []).append(user)
            self._by_code.setdefault(user.employee_code.strip().lower(), []).append(user)
            self._by_name.setdefault(user.full_name.strip().lower(), []).append(user)

    def resolve(self, raw: str | None) -> tuple[DirectoryUser | None, str | None]:
        """Returns (user, problem). Exactly one of the two is set.

        Resolution order: exact email -> exact employee code -> unique
        full-name match. Multiple name matches => ambiguous (problem).
        Zero matches => unresolved (problem). Never guessed.
        """
        text = (raw or "").strip()
        if not text:
            return None, "No value provided."
        lowered = text.lower()
        if "@" in text:
            matches = self._by_email.get(lowered, [])
            if len(matches) == 1:
                return self._check_active(matches[0])
            return None, f"No user directory entry for email '{text}'."
        by_code = self._by_code.get(lowered, [])
        if len(by_code) == 1:
            return self._check_active(by_code[0])
        by_name = self._by_name.get(lowered, [])
        if len(by_name) == 1:
            return self._check_active(by_name[0])
        if len(by_name) > 1:
            names = ", ".join(sorted(u.email for u in by_name))
            return None, f"Ambiguous name '{text}' matches {len(by_name)} users ({names})."
        if len(by_code) > 1:
            return None, f"Ambiguous employee code '{text}'."
        return None, f"Name '{text}' does not match any directory user."

    @staticmethod
    def _check_active(user: DirectoryUser) -> tuple[DirectoryUser | None, str | None]:
        if not user.is_active:
            return None, f"User '{user.full_name}' ({user.email}) is not active."
        return user, None


# ---------------------------------------------------------------------------
# Duplicate detection (spec pipeline step 9: legacy identifiers +
# configurable matching rules)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExistingTaskRef:
    task_id: str
    task_number: str
    title: str
    due_date: str | None = None
    legacy_external_id: str | None = None


@dataclass
class DuplicateMatch:
    kind: str            # exact_task_number | exact_legacy_id | likely | possible
    task: ExistingTaskRef
    reason: str


class DuplicateIndex:
    """Existing-task snapshot used for duplicate detection (built by the
    service from the DB once per validation pass)."""

    def __init__(self, tasks: list[ExistingTaskRef], *, match_title_due: bool = True,
                 match_title_only: bool = False) -> None:
        self.tasks = tasks
        self.match_title_due = match_title_due
        self.match_title_only = match_title_only
        self._by_number = {t.task_number.strip().upper(): t for t in tasks}
        self._by_legacy = {}
        for t in tasks:
            if t.legacy_external_id:
                self._by_legacy.setdefault(t.legacy_external_id.strip().upper(), []).append(t)
        self._by_title: dict[str, list[ExistingTaskRef]] = {}
        for t in tasks:
            self._by_title.setdefault(_norm_title(t.title), []).append(t)

    def find(self, legacy_id: str | None, title: str, due_date: date | None) -> list[DuplicateMatch]:
        matches: list[DuplicateMatch] = []
        seen: set[str] = set()

        def add(kind: str, ref: ExistingTaskRef, reason: str) -> None:
            if ref.task_id in seen:
                return
            seen.add(ref.task_id)
            matches.append(DuplicateMatch(kind=kind, task=ref, reason=reason))

        legacy = (legacy_id or "").strip().upper()
        if legacy:
            if legacy in self._by_number:
                add("exact_task_number", self._by_number[legacy],
                    f"Task ID {legacy} matches an existing task_number.")
            for ref in self._by_legacy.get(legacy, []):
                add("exact_legacy_id", ref,
                    f"Task ID {legacy} was already imported (legacy_external_id).")

        normalized_title = _norm_title(title) if title else None
        if normalized_title:
            due_key = due_date.isoformat() if due_date else ""
            for ref in self._by_title.get(normalized_title, []):
                ref_due = ref.due_date or ""
                if self.match_title_due and due_key and ref_due == due_key:
                    add("likely", ref,
                        f"Same normalized title and due date as existing {ref.task_number}.")
                elif self.match_title_only:
                    add("possible", ref,
                        f"Same normalized title as existing {ref.task_number}.")

        return matches


def _norm_title(title: str) -> str:
    return re.sub(r"\s+", " ", (title or "").strip().lower())


# ---------------------------------------------------------------------------
# Row validation (spec pipeline steps 4-8: normalize, resolve, validate)
# ---------------------------------------------------------------------------

ROW_OK = "ok"
ROW_WARNING = "warning"
ROW_FAILED = "failed"


@dataclass
class NormalizedRow:
    """Validated, normalized values ready for commit."""
    legacy_task_id: str | None = None
    title: str = ""
    description: str | None = None
    priority: str = "medium"
    status: str = "open"
    percent_complete: int = 0
    percent_requires_reconciliation: bool = False
    accountable_pm_id: str | None = None
    accountable_pm_display: str | None = None
    supporting_pm_ids: list[str] = field(default_factory=list)
    supporting_pm_display: list[str] = field(default_factory=list)
    assigned_by_id: str | None = None
    start_date: str | None = None
    due_date: str | None = None
    next_follow_up_date: str | None = None
    date_created: str | None = None
    last_updated: str | None = None
    completion_date: str | None = None
    dependency_summary: str | None = None
    attachment_folder_reference: str | None = None
    # Soft-duplicate rows need an explicit operator decision before commit
    duplicate_review: bool = False


@dataclass
class RowReport:
    """Per-row outcome (spec pipeline step 10: row-level validation report)."""
    row_number: int
    source_task_id: str | None
    title: str
    status: str                       # ROW_OK / ROW_WARNING / ROW_FAILED
    errors: list[str] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
    duplicates: list[dict] = field(default_factory=list)
    normalized: NormalizedRow | None = None
    # Filled at commit time
    outcome: str | None = None        # committed / skipped_duplicate / already_committed / failed
    committed_task_number: str | None = None
    committed_task_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "row_number": self.row_number,
            "source_task_id": self.source_task_id,
            "title": self.title,
            "status": self.status,
            "errors": list(self.errors),
            "notices": list(self.notices),
            "duplicates": list(self.duplicates),
            "normalized": _row_to_dict(self.normalized),
            "outcome": self.outcome,
            "committed_task_number": self.committed_task_number,
            "committed_task_id": self.committed_task_id,
        }


def _row_to_dict(row: NormalizedRow | None) -> dict | None:
    if row is None:
        return None
    return {k: v for k, v in row.__dict__.items() if v is not None and v != []}


def validate_row(
    row: dict[str, str],
    *,
    row_number: int,
    mapping: dict[str, str | None],
    directory: UserDirectory,
    duplicates: DuplicateIndex,
    day_first: bool = True,
) -> RowReport:
    """Validate and normalize one spreadsheet row (never raises).

    Warnings are committable notices; errors make the row non-committable.
    Every problem is recorded — no row is ever silently discarded (spec).
    """
    report = RowReport(row_number=row_number, source_task_id=None, title="", status=ROW_OK)

    # ---- invert mapping: target field -> raw cell value -------------------
    cells: dict[str, str] = {}
    for header, target in mapping.items():
        if not target:
            continue
        value = (row.get(header) or "").strip()
        if target in cells and value:
            report.errors.append(
                f"Column '{header}' maps to '{target}' which another column already provides."
            )
        cells.setdefault(target, value)

    title_raw = cells.get("title", "")
    report.title = re.sub(r"\s+", " ", title_raw).strip()

    legacy_id = cells.get("legacy_task_id", "") or None
    report.source_task_id = legacy_id

    # ---- required fields ---------------------------------------------------
    if not report.title:
        report.errors.append("Task Title is required.")
    if len(report.title) > 300:
        report.errors.append("Task Title exceeds the 300 character limit.")

    # ---- people resolution ---------------------------------------------------
    accountable: DirectoryUser | None = None
    pm_raw = cells.get("accountable_pm", "")
    if not pm_raw:
        report.errors.append("Accountable PM is required.")
    else:
        user, problem = directory.resolve(pm_raw)
        if problem or user is None:
            report.errors.append(f"Accountable PM: {problem}")
        else:
            accountable = user

    supporting_ids: list[str] = []
    supporting_display: list[str] = []
    for name in split_people(cells.get("supporting_pms")):
        user, problem = directory.resolve(name)
        if problem or user is None:
            report.errors.append(f"Supporting PM '{name}': {problem}")
        elif user.user_id == (accountable.user_id if accountable else None):
            report.notices.append(
                f"Supporting PM '{name}' is also the accountable PM; skipped duplicate assignment."
            )
        elif user.user_id in supporting_ids:
            report.notices.append(f"Supporting PM '{name}' listed twice; kept one entry.")
        else:
            supporting_ids.append(user.user_id)
            supporting_display.append(user.full_name)

    assigned_by_id: str | None = None
    assigned_by_raw = cells.get("assigned_by", "")
    if assigned_by_raw:
        user, problem = directory.resolve(assigned_by_raw)
        if problem or user is None:
            # The historical assigner is provenance metadata, not an access
            # decision: unresolved names degrade to the import actor + notice.
            report.notices.append(
                f"Assigned By '{assigned_by_raw}' unresolved; recorded against the import actor."
            )
        else:
            assigned_by_id = user.user_id

    # ---- dates ---------------------------------------------------------------
    def _required_date(target: str, label: str) -> date | None:
        raw = cells.get(target, "")
        try:
            return parse_optional_date(raw, day_first=day_first)
        except RowError as exc:
            report.errors.append(f"{label}: {exc}")
            return None

    due_date = _required_date("due_date", "Due Date")
    start_date = _required_date("start_date", "Start Date")
    date_created = _required_date("date_created", "Date Created")
    completion_date = _required_date("completion_date", "Completion Date")
    follow_up = _required_date("next_follow_up_date", "Next Follow-up Date")

    # ---- status / priority / percent ----------------------------------------
    status = "open"
    try:
        status = normalize_status(cells.get("status"))
        if not (cells.get("status") or "").strip():
            report.notices.append("Empty status defaulted to 'open'.")
    except RowError as exc:
        report.errors.append(str(exc))

    priority = "medium"
    try:
        priority, defaulted = normalize_priority(cells.get("priority"))
        if defaulted:
            report.notices.append("Empty priority defaulted to 'medium'.")
    except RowError as exc:
        report.errors.append(str(exc))

    percent = 0
    reconcilable = False
    try:
        percent, reconcilable = normalize_percent(cells.get("percent_complete"))
        if reconcilable:
            report.notices.append(
                "Historical percentage imported; reconcile against the new workflow calculation."
            )
    except RowError as exc:
        report.errors.append(str(exc))

    # ---- date relationships ----------------------------------------------------
    if start_date and due_date and start_date > due_date:
        report.errors.append(
            f"Start Date {start_date.isoformat()} is after Due Date {due_date.isoformat()}."
        )
    if completion_date and start_date and completion_date < start_date:
        report.errors.append(
            f"Completion Date {completion_date.isoformat()} is before Start Date {start_date.isoformat()}."
        )
    if status == "completed" and not completion_date:
        report.notices.append(
            "Status is completed but no Completion Date was provided; completion timestamp omitted."
        )
    if not due_date:
        report.notices.append("Due Date missing; task will be created without a deadline.")

    # ---- verbatim legacy references (untrusted; stored, never fetched) ------
    dependency = cells.get("dependency_summary", "") or None
    attachment_ref = cells.get("attachment_folder_reference", "") or None
    if dependency and len(dependency) > 2000:
        report.errors.append("Dependency / Blocker description exceeds 2000 characters.")
    if attachment_ref and len(attachment_ref) > 500:
        report.errors.append("Attachment / Folder Link exceeds 500 characters.")
    if attachment_ref and re.match(r"https?://", attachment_ref, re.I):
        report.notices.append(
            "Attachment link is an external URL stored as an untrusted reference (never fetched)."
        )

    # ---- duplicates -----------------------------------------------------------
    dup_matches = duplicates.find(legacy_id, report.title, due_date)
    blocking_dup = [d for d in dup_matches if d.kind in ("exact_task_number", "exact_legacy_id")]
    soft_dups = [d for d in dup_matches if d.kind not in ("exact_task_number", "exact_legacy_id")]
    for dup in dup_matches:
        report.duplicates.append({
            "kind": dup.kind,
            "task_number": dup.task.task_number,
            "title": dup.task.title,
            "reason": dup.reason,
        })
    if blocking_dup:
        # Exact identifier match: committing would duplicate a known task.
        report.status = ROW_FAILED
        report.errors.append(
            "Duplicate: " + "; ".join(d.reason for d in blocking_dup)
        )
    elif soft_dups:
        report.notices.append(
            "Possible duplicate detected; excluded from commit unless the operator keeps it."
        )

    # ---- verdict ---------------------------------------------------------------
    if report.errors and report.status != ROW_FAILED:
        report.status = ROW_FAILED
    elif report.notices and report.status != ROW_FAILED:
        report.status = ROW_WARNING

    if report.status != ROW_FAILED and accountable is not None:
        soft_dup = bool(soft_dups)  # soft duplicates need operator review
        report.normalized = NormalizedRow(
            legacy_task_id=legacy_id,
            title=report.title,
            description=cells.get("description", "") or None,
            priority=priority,
            status=status,
            percent_complete=percent,
            percent_requires_reconciliation=reconcilable,
            accountable_pm_id=accountable.user_id,
            accountable_pm_display=accountable.full_name,
            supporting_pm_ids=supporting_ids,
            supporting_pm_display=supporting_display,
            assigned_by_id=assigned_by_id,
            start_date=start_date.isoformat() if start_date else None,
            due_date=due_date.isoformat() if due_date else None,
            next_follow_up_date=follow_up.isoformat() if follow_up else None,
            date_created=date_created.isoformat() if date_created else None,
            last_updated=(cells.get("last_updated", "") or None),
            completion_date=completion_date.isoformat() if completion_date else None,
            dependency_summary=dependency,
            attachment_folder_reference=attachment_ref,
            duplicate_review=soft_dup,
        )

    return report


def count_rows(reports: list[RowReport]) -> dict[str, int]:
    return {
        "total": len(reports),
        "successful": sum(1 for r in reports if r.status == ROW_OK),
        "warning": sum(1 for r in reports if r.status == ROW_WARNING),
        "failed": sum(1 for r in reports if r.status == ROW_FAILED),
    }
