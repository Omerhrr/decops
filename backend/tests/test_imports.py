""" CSV Migration: domain validation engine + import center API.

Covers the product requirements spreadsheet_migration pipeline and rules:
- approved mapping tables (status/priority), normalization, date parsing;
- user resolution never invents mappings for ambiguous names;
- duplicate detection via legacy identifiers + configurable rules;
- row-level validation report - invalid rows are never silently discarded;
- commit creates tasks with preserved historical data, approved visibility,
  and verbatim untrusted references; retry-safe without duplicates;
- imports cannot grant unauthorized access (no extra grants; restricted
  tasks stay restricted after import).
"""

import io
import uuid
from datetime import date, datetime

import pytest
from sqlalchemy import select, text

from app.domain import csv_import as ci
from app.domain.task_lifecycle import TaskStatus
from app.models import AuditEvent, Task, TaskActivity, TaskAssignment, TaskPriority
from app.services import import_service

from tests.conftest import login, make_user

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

CSV_HEADERS = list(ci.SOURCE_COLUMNS)


def write_csv(rows: list[dict]) -> tuple[str, bytes]:
    """rows: list of {header: value}; returns (filename, bytes)."""
    def esc(value):
        value = "" if value is None else str(value)
        return f'"{value}"' if ("," in value or '"' in value) else value

    lines = [",".join(CSV_HEADERS)]
    for row in rows:
        lines.append(",".join(esc(row.get(h, "")) for h in CSV_HEADERS))
    return "legacy-tasks.csv", ("\n".join(lines) + "\n").encode("utf-8")


def upload(client, rows: list[dict], **form_fields):
    name, content = write_csv(rows)
    return client.post(
        "/api/v1/imports/csv",
        files={"file": (name, io.BytesIO(content), "text/csv")},
        data=form_fields or None,
    )


@pytest.fixture()
def admin(test_db, client):
    """Company Administrator (holds imports.manage + imports.view)."""
    user = make_user(
        test_db,
        email="importer@interdec.com",
        employee_code="INT-IMP1",
        role_names=["Company Administrator"],
    )
    response = login(client, "importer@interdec.com", "Secret!1234")
    assert response.status_code == 200, response.text
    return user


@pytest.fixture()
def people(test_db):
    """Small directory: two named people + one inactive."""
    ann = make_user(test_db, email="ann.chen@interdec.com", employee_code="INT-A1",
                    role_names=["Accountable PM"])
    bob = make_user(test_db, email="bob.ray@interdec.com", employee_code="INT-B1",
                    role_names=["Supporting PM"])
    make_user(test_db, email="retired@interdec.com", employee_code="INT-R1", status="inactive")
    return {"ann": ann, "bob": bob}


@pytest.fixture()
def isolated_storage(monkeypatch, tmp_path):
    """Point the import storage at a temp dir for the duration of a test."""
    from app.core.config import Settings

    settings = Settings(environment="testing", import_storage_dir=tmp_path / "imports")
    monkeypatch.setattr(import_service, "get_settings", lambda: settings)
    return tmp_path / "imports"


VALID_ROW = {
    "Task ID": "LEG-201",
    "Date Created": "2025-01-15",
    "Task Title": "Replace conveyor belt",
    "Task Description": "Section 3 belt replacement",
    "Priority": "P1",
    "Accountable PM": "ann.chen@interdec.com",
    "Supporting PM(s)": "bob.ray@interdec.com",
    "Assigned By": "",
    "Start Date": "2025-02-01",
    "Due Date": "2025-03-01",
    "Status": "In Progress",
    "% Complete": "40",
    "Last Updated": "2025-02-20",
    "Next Follow-up Date": "",
    "Dependency / Blocker": "Waiting on belt part",
    "Attachment / Folder Link": "https://legacy.interdec.com/f/belt",
    "Completion Date": "",
}


# ---------------------------------------------------------------------------
# Domain: mapping tables, normalization, resolution, duplicates
# ---------------------------------------------------------------------------

class TestHeaderMapping:
    def test_spec_columns_map_to_default_targets(self):
        mapping = ci.auto_map_headers(list(ci.SOURCE_COLUMNS))
        assert mapping == dict(ci.DEFAULT_COLUMN_MAPPING)

    def test_aliases_and_duplicates(self):
        mapping = ci.auto_map_headers(["Task Name", "Task Name", "Unknown Col"])
        assert mapping["Task Name"] == "title"
        assert mapping["Unknown Col"] is None
        assert list(mapping.values()).count("title") == 1


class TestNormalization:
    def test_status_mapping(self):
        assert ci.normalize_status("In Progress") == "in_progress"
        assert ci.normalize_status("done") == "completed"
        assert ci.normalize_status("On Hold") == "blocked"
        assert ci.normalize_status("canceled") == "cancelled"  # spelling variant
        with pytest.raises(ci.RowError, match="Unmapped legacy status"):
            ci.normalize_status("weird state")
        assert ci.normalize_status("") == "open"

    def test_priority_mapping(self):
        assert ci.normalize_priority("P1") == ("high", False)
        assert ci.normalize_priority("urgent") == ("critical", False)
        assert ci.normalize_priority("") == ("medium", True)
        with pytest.raises(ci.RowError, match="Unmapped legacy priority"):
            ci.normalize_priority("ASAP!")

    def test_percent_normalization_and_reconciliation_flag(self):
        assert ci.normalize_percent("35%") == (35, True)
        assert ci.normalize_percent("0.35") == (35, True)
        assert ci.normalize_percent("100") == (100, True)
        assert ci.normalize_percent("") == (0, False)
        with pytest.raises(ci.RowError):
            ci.normalize_percent("140")

    def test_date_parsing_day_first(self):
        assert ci.parse_date("2025-03-14").isoformat() == "2025-03-14"
        assert ci.parse_date("14/03/2025").isoformat() == "2025-03-14"
        assert ci.parse_date("03/14/2025", day_first=False).isoformat() == "2025-03-14"
        with pytest.raises(ci.RowError):
            ci.parse_date("13/13/2025")
        with pytest.raises(ci.RowError):
            ci.parse_date("not a date")

    def test_split_people(self):
        assert ci.split_people("Ann; Bob") == ["Ann", "Bob"]
        assert ci.split_people("Ann, Bob") == ["Ann", "Bob"]
        assert ci.split_people("") == []


class TestUserResolution:
    def _directory(self):
        return ci.UserDirectory(users=[
            ci.DirectoryUser("u-ann", "Ann Chen", "ann@interdec.com", "INT-A1", True),
            ci.DirectoryUser("u-bob1", "Bob Ray", "bob1@interdec.com", "INT-B1", True),
            ci.DirectoryUser("u-bob2", "Bob Ray", "bob2@interdec.com", "INT-B2", True),
            ci.DirectoryUser("u-old", "Old Guy", "old@interdec.com", "INT-O1", False),
        ])

    def test_email_exact(self):
        user, problem = self._directory().resolve("ANN@interdec.com")
        assert user and user.user_id == "u-ann" and problem is None

    def test_unique_name(self):
        user, problem = self._directory().resolve("Ann Chen")
        assert user and user.user_id == "u-ann"

    def test_ambiguous_name_never_invented(self):
        user, problem = self._directory().resolve("Bob Ray")
        assert user is None
        assert "Ambiguous" in problem

    def test_unknown_user(self):
        user, problem = self._directory().resolve("Nobody Here")
        assert user is None and "does not match" in problem

    def test_inactive_user_rejected(self):
        user, problem = self._directory().resolve("old@interdec.com")
        assert user is None and "not active" in problem


class TestDuplicateDetection:
    def _index(self, **kwargs):
        return ci.DuplicateIndex(
            [ci.ExistingTaskRef("t-1", "TSK-2026-0001", "Fix the pump", "2025-04-01", "LEG-9")],
            **kwargs,
        )

    def test_exact_task_number(self):
        matches = self._index().find("tsk-2026-0001", "Different", None)
        assert matches and matches[0].kind == "exact_task_number"

    def test_exact_legacy_id(self):
        matches = self._index().find("LEG-9", "Different", None)
        assert matches and matches[0].kind == "exact_legacy_id"

    def test_likely_title_and_due(self):
        matches = self._index().find(None, "fix the  pump", date(2025, 4, 1))
        assert matches and matches[0].kind == "likely"

    def test_title_only_disabled_by_default(self):
        # Title matches but the due date differs: title-only rule is off by
        # default, so no duplicate is reported.
        assert self._index().find(None, "fix the pump", date(2025, 9, 9)) == []

    def test_title_only_when_enabled(self):
        index = self._index(match_title_due=False, match_title_only=True)
        matches = index.find(None, "fix the pump", date(2025, 4, 1))
        assert matches and matches[0].kind == "possible"


# ---------------------------------------------------------------------------
# Domain: full row validation
# ---------------------------------------------------------------------------

class TestValidateRow:
    def _validate(self, row_overrides: dict | None = None, index=None):
        directory = ci.UserDirectory(users=[
            ci.DirectoryUser("u-ann", "Ann Chen", "ann.chen@interdec.com", "INT-A1", True),
            ci.DirectoryUser("u-bob", "Bob Ray", "bob.ray@interdec.com", "INT-B1", True),
        ])
        row = {h: "" for h in CSV_HEADERS}
        row.update(VALID_ROW)
        row.update(row_overrides or {})
        return ci.validate_row(
            row, row_number=2, mapping=dict(ci.DEFAULT_COLUMN_MAPPING),
            directory=directory, duplicates=index or ci.DuplicateIndex([]),
        )

    def test_valid_row_is_ok_with_normalized_values(self):
        report = self._validate({"% Complete": "", "Attachment / Folder Link": ""})
        assert report.status == ci.ROW_OK, (report.status, report.errors, report.notices)
        n = report.normalized
        assert n.title == "Replace conveyor belt"
        assert n.priority == "high"
        assert n.status == "in_progress"
        assert n.accountable_pm_id == "u-ann"
        assert n.supporting_pm_ids == ["u-bob"]
        assert n.due_date == "2025-03-01"

    def test_missing_title_fails(self):
        report = self._validate({"Task Title": "   "})
        assert report.status == ci.ROW_FAILED
        assert any("Task Title is required" in e for e in report.errors)

    def test_missing_accountable_pm_fails(self):
        report = self._validate({"Accountable PM": ""})
        assert report.status == ci.ROW_FAILED
        assert any("Accountable PM is required" in e for e in report.errors)

    def test_unmapped_status_fails_and_is_reported(self):
        report = self._validate({"Status": "weird state"})
        assert report.status == ci.ROW_FAILED
        assert any("Unmapped legacy status 'weird state'" in e for e in report.errors)

    def test_start_after_due_fails(self):
        report = self._validate({"Start Date": "2025-04-01"})
        assert report.status == ci.ROW_FAILED
        assert any("Start Date" in e and "after Due Date" in e for e in report.errors)

    def test_completion_before_start_fails(self):
        report = self._validate({"Status": "Completed", "Completion Date": "2025-01-01"})
        assert report.status == ci.ROW_FAILED
        assert any("Completion Date" in e for e in report.errors)

    def test_ambiguous_supporting_pm_fails(self):
        report = self._validate({"Supporting PM(s)": "Mystery Person"})
        assert report.status == ci.ROW_FAILED
        assert any("Mystery Person" in e for e in report.errors)

    def test_supporting_pm_duplicated_gets_notice(self):
        report = self._validate({"Supporting PM(s)": "bob.ray@interdec.com; Bob Ray"})
        assert report.status == ci.ROW_WARNING  # notices => warning; still committable
        assert any("listed twice" in nt for nt in report.notices)

    def test_percent_reconciliation_notice(self):
        report = self._validate()
        assert report.normalized.percent_requires_reconciliation is True
        assert any("reconcile" in nt for nt in report.notices)

    def test_external_link_flagged_untrusted(self):
        report = self._validate()
        assert any("untrusted reference" in nt for nt in report.notices)

    def test_missing_due_date_warns(self):
        report = self._validate({"Due Date": "", "% Complete": "",
                                 "Attachment / Folder Link": ""})
        assert report.status == ci.ROW_WARNING
        assert any("Due Date missing" in nt for nt in report.notices)

    def test_blocking_duplicate_fails(self):
        index = ci.DuplicateIndex([
            ci.ExistingTaskRef("t-9", "LEG-201", "Other title", None, "LEG-201"),
        ])
        report = self._validate(index=index)
        assert report.status == ci.ROW_FAILED
        assert report.duplicates
        assert any("Duplicate" in e for e in report.errors)

    def test_soft_duplicate_requires_review(self):
        index = ci.DuplicateIndex(
            [ci.ExistingTaskRef("t-9", "TSK-2026-0005", "Replace conveyor belt", "2025-03-01")],
        )
        report = self._validate(index=index)
        assert report.status == ci.ROW_WARNING
        assert report.normalized.duplicate_review is True
        assert report.duplicates[0]["kind"] == "likely"

    def test_whitespace_normalized(self):
        report = self._validate({"Task Title": "  Replace   conveyor   belt "})
        assert report.normalized.title == "Replace conveyor belt"


# ---------------------------------------------------------------------------
# API: file handling, permissions, validation report
# ---------------------------------------------------------------------------

class TestUploadValidation:
    def test_requires_authentication(self, client, isolated_storage):
        name, content = write_csv([VALID_ROW])
        response = client.post(
            "/api/v1/imports/csv",
            files={"file": (name, io.BytesIO(content), "text/csv")},
        )
        assert response.status_code == 401

    def test_requires_imports_manage(self, test_db, client, isolated_storage):
        make_user(test_db, email="member@interdec.com", employee_code="INT-M9",
                  role_names=["Department Member"])
        login(client, "member@interdec.com", "Secret!1234")
        name, content = write_csv([VALID_ROW])
        response = client.post(
            "/api/v1/imports/csv",
            files={"file": (name, io.BytesIO(content), "text/csv")},
        )
        assert response.status_code == 404  # non-enumerating permission denial

    def test_system_administrator_cannot_see_imports(self, test_db, client, isolated_storage):
        """Spec restriction: technical administration must not automatically
        imply access to confidential business content (import reports carry
        titles/people), so System Administration holds no imports.view."""
        make_user(test_db, email="sysadmin@interdec.com", employee_code="INT-S9",
                  role_names=["System Administrator"])
        login(client, "sysadmin@interdec.com", "Secret!1234")
        response = client.get("/api/v1/imports")
        assert response.status_code == 404

    def test_rejects_non_csv(self, client, admin, isolated_storage):
        response = client.post(
            "/api/v1/imports/csv",
            files={"file": ("data.xlsx", io.BytesIO(b"binary"), "application/octet-stream")},
        )
        assert response.status_code == 422
        assert "csv" in response.json()["error"]["message"].lower()

    def test_rejects_empty_file(self, client, admin, isolated_storage):
        response = client.post(
            "/api/v1/imports/csv",
            files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
        )
        assert response.status_code == 422

    def test_rejects_non_utf8(self, client, admin, isolated_storage):
        name, content = write_csv([VALID_ROW])
        latin1 = content.decode("utf-8").encode("latin-1")
        latin1 = latin1.replace(b"belt", "bélt".encode("latin-1"))
        response = client.post(
            "/api/v1/imports/csv",
            files={"file": (name, io.BytesIO(latin1), "text/csv")},
        )
        assert response.status_code == 422
        assert "utf-8" in response.json()["error"]["message"].lower()

    def test_upload_validates_and_returns_counts(self, client, admin, people, isolated_storage):
        response = upload(client, [VALID_ROW])
        assert response.status_code == 201, response.text
        job = response.json()
        assert job["status"] == "validated"
        assert job["total_rows"] == 1
        assert job["warning_rows"] == 1  # percent reconciliation + untrusted link
        assert job["failed_rows"] == 0

    def test_row_report_contains_notices_and_normalized_preview(
        self, client, admin, people, isolated_storage,
    ):
        job = upload(client, [VALID_ROW]).json()
        report = client.get(f"/api/v1/imports/{job['id']}/report").json()
        row = report["rows"][0]
        assert row["status"] == "warning"
        assert any("reconcile" in nt for nt in row["notices"])
        assert row["normalized"]["priority"] == "high"
        assert row["normalized"]["status"] == "in_progress"

    def test_failed_rows_never_silently_discarded(
        self, client, admin, people, isolated_storage,
    ):
        bad_status = dict(VALID_ROW, **{"Task ID": "LEG-301", "Status": "weird state",
                                        "Task Title": "Row A"})
        no_title = dict(VALID_ROW, **{"Task ID": "LEG-302", "Task Title": ""})
        unknown_pm = dict(VALID_ROW, **{"Task ID": "LEG-303", "Task Title": "Row B",
                                        "Accountable PM": "Nobody Known"})
        good = dict(VALID_ROW, **{"Task ID": "LEG-304", "Task Title": "Row C"})
        job = upload(client, [bad_status, no_title, unknown_pm, good]).json()
        assert job["total_rows"] == 4
        assert job["failed_rows"] == 3
        # The good row carries notices (percent reconciliation, untrusted
        # link) => counted as warning, still committable at commit time.
        assert job["successful_rows"] == 0
        assert job["warning_rows"] == 1
        report = client.get(f"/api/v1/imports/{job['id']}/report").json()
        failed = [r for r in report["rows"] if r["status"] == "failed"]
        assert len(failed) == 3
        all_errors = " ".join(e for r in failed for e in r["errors"])
        assert "Unmapped legacy status" in all_errors
        assert "Task Title is required" in all_errors
        assert "does not match any directory user" in all_errors

    def test_mapping_override_and_revalidation(self, client, admin, people, isolated_storage):
        weird = dict(VALID_ROW, **{"Priority": "Operations", "Task ID": "LEG-401"})
        job = upload(client, [weird]).json()
        assert job["failed_rows"] == 1  # "operations" is not in the priority table
        response = client.patch(
            f"/api/v1/imports/{job['id']}",
            json={"mapping": {"Priority": None}},
        )
        assert response.status_code == 200, response.text
        job = response.json()
        assert job["failed_rows"] == 0
        assert job["warning_rows"] == 1  # notices only (percent, link, default priority)

    def test_patch_committed_job_conflict(self, client, admin, people, isolated_storage):
        job = upload(client, [VALID_ROW]).json()
        commit = client.post(f"/api/v1/imports/{job['id']}/commit")
        assert commit.status_code == 200
        response = client.patch(f"/api/v1/imports/{job['id']}", json={"options": {}})
        assert response.status_code == 409

    def test_unknown_mapping_header_rejected(self, client, admin, people, isolated_storage):
        job = upload(client, [VALID_ROW]).json()
        response = client.patch(
            f"/api/v1/imports/{job['id']}",
            json={"mapping": {"Not A Column": "title"}},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# API: commit semantics
# ---------------------------------------------------------------------------

class TestCommit:
    def _upload_and_commit(self, client, rows, **upload_kwargs):
        job = upload(client, rows, **upload_kwargs).json()
        response = client.post(f"/api/v1/imports/{job['id']}/commit")
        return job, response

    def test_commit_creates_tasks_with_preserved_history(
        self, test_db, client, admin, people, isolated_storage,
    ):
        job, response = self._upload_and_commit(client, [VALID_ROW])
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["committed_rows"] == 1

        task = test_db.get(Task, uuid.UUID(result["task_ids"][0]))
        assert task.task_number == "TSK-2026-0001"  # allocated (legacy id not TSK pattern)
        assert task.legacy_external_id == "LEG-201"
        assert str(getattr(task.status, "value", task.status)) == "in_progress"
        assert str(getattr(task.priority, "value", task.priority)) == "high"
        assert task.percent_complete == 40
        assert str(getattr(task.progress_mode, "value", task.progress_mode)) == "manual"
        assert task.dependency_summary == "Waiting on belt part"
        assert task.attachment_folder_reference == "https://legacy.interdec.com/f/belt"
        assert task.created_at.date() == datetime(2025, 1, 15).date()  # historical preserved
        assert str(getattr(task.visibility_mode, "value", task.visibility_mode)) == "participants"

        assignments = test_db.query(TaskAssignment).filter_by(task_id=task.id).all()
        roles = {str(getattr(a.assignment_role, "value", a.assignment_role)) for a in assignments}
        assert roles == {"accountable_pm", "supporting_pm"}
        accountable = next(a for a in assignments
                           if str(getattr(a.assignment_role, "value", a.assignment_role)) == "accountable_pm")
        assert accountable.user_id == people["ann"].id
        supporting = next(a for a in assignments
                          if str(getattr(a.assignment_role, "value", a.assignment_role)) == "supporting_pm")
        assert supporting.user_id == people["bob"].id

    def test_commit_creates_import_activity_not_fabricated_history(
        self, test_db, client, admin, people, isolated_storage,
    ):
        job, response = self._upload_and_commit(client, [VALID_ROW])
        task = test_db.get(Task, uuid.UUID(response.json()["task_ids"][0]))
        activities = test_db.query(TaskActivity).filter_by(task_id=task.id).all()
        imported = [a for a in activities if a.activity_type == "task.imported"]
        assert imported, "import provenance activity must be recorded"
        assert "legacy spreadsheet" in imported[0].summary
        assert imported[0].actor_id == admin.id  # import actor, not a historical actor
        detail = imported[0].detail or {}
        assert detail.get("percent_requires_reconciliation") is True

    def test_retry_safe_no_duplicates(self, test_db, client, admin, people, isolated_storage):
        job, first = self._upload_and_commit(client, [VALID_ROW])
        assert first.status_code == 200
        # Second commit attempt is refused outright (already committed).
        second = client.post(f"/api/v1/imports/{job['id']}/commit")
        assert second.status_code == 409
        # Re-uploading the same legacy file detects the exact legacy id.
        reupload = upload(client, [VALID_ROW])
        assert reupload.json()["failed_rows"] == 1
        report = client.get(f"/api/v1/imports/{reupload.json()['id']}/report").json()
        kinds = {d["kind"] for d in report["rows"][0]["duplicates"]}
        assert "exact_legacy_id" in kinds

    def test_duplicates_and_failed_rows_excluded_from_commit(
        self, test_db, client, admin, people, isolated_storage,
    ):
        test_db.add(Task(
            task_number="TSK-2026-0050", title="Existing task",
            priority=TaskPriority.medium, status=TaskStatus.open,
            accountable_pm_id=people["ann"].id, created_by_id=admin.id,
            visibility_mode="participants", due_date=date(2025, 4, 1),
        ))
        test_db.commit()

        likely_dup = dict(VALID_ROW, **{
            "Task ID": "LEG-911", "Task Title": "Existing task", "Due Date": "2025-04-01",
        })
        job, response = self._upload_and_commit(client, [VALID_ROW, likely_dup])
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["committed_rows"] == 1
        titles = test_db.scalars(select(Task.title).where(Task.title == "Existing task")).all()
        assert len(titles) == 1  # the pre-existing task; duplicate was never created

        report = client.get(f"/api/v1/imports/{job['id']}/report").json()
        dup_row = next(r for r in report["rows"] if r["source_task_id"] == "LEG-911")
        assert dup_row["duplicates"][0]["kind"] == "likely"
        assert dup_row["normalized"]["duplicate_review"] is True

    def test_import_cannot_grant_unauthorized_access(
        self, test_db, client, admin, people, isolated_storage,
    ):
        """Imported task must not be visible to users without a legitimate
        relationship - no access grants are created by the import."""
        make_user(test_db, email="outsider@interdec.com", employee_code="INT-O9",
                  role_names=["Department Member"])
        job, response = self._upload_and_commit(client, [VALID_ROW])
        task_id = response.json()["task_ids"][0]
        grants = test_db.execute(
            text("SELECT COUNT(*) FROM task_access_grants WHERE task_id = :tid"),
            {"tid": task_id},
        ).scalar()
        assert grants == 0
        login(client, "outsider@interdec.com", "Secret!1234")
        leak = client.get(f"/api/v1/tasks/{task_id}")
        assert leak.status_code == 404

    def test_audited_import_events(self, test_db, client, admin, people, isolated_storage):
        job, response = self._upload_and_commit(client, [VALID_ROW])
        actions = [a.action for a in test_db.query(AuditEvent).all()]
        assert "import.created" in actions
        assert "import.committed" in actions
        assert "task.created" in actions

    def test_commit_with_no_eligible_rows_conflicts(self, client, admin, people, isolated_storage):
        broken = dict(VALID_ROW, **{"Status": "garbage"})
        job = upload(client, [broken]).json()
        response = client.post(f"/api/v1/imports/{job['id']}/commit")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "nothing_to_commit"

    def test_report_download(self, client, admin, people, isolated_storage):
        job = upload(client, [VALID_ROW]).json()
        response = client.get(f"/api/v1/imports/{job['id']}/report/download")
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "attachment" in response.headers["content-disposition"]
        assert "Row,Source Task ID,Task Title" in response.text
        assert "Replace conveyor belt" in response.text

    def test_import_history_lists_jobs(self, client, admin, people, isolated_storage):
        upload(client, [VALID_ROW])
        listing = client.get("/api/v1/imports")
        assert listing.status_code == 200
        jobs = listing.json()
        assert len(jobs) >= 1
        assert {"id", "filename", "status", "total_rows", "committed_rows"} <= set(jobs[0])

    def test_legacy_task_number_reuse(self, test_db, client, admin, people, isolated_storage):
        """A legacy Task ID matching the TSK-YYYY-NNNN pattern and unallocated
        becomes the new task_number."""
        row = dict(VALID_ROW, **{"Task ID": "TSK-2024-0777"})
        job, response = self._upload_and_commit(client, [row])
        assert response.status_code == 200
        task = test_db.get(Task, uuid.UUID(response.json()["task_ids"][0]))
        assert task.task_number == "TSK-2024-0777"
        assert task.legacy_external_id is None  # identifier lives as task_number


class TestIntraFileDuplicates:
    def test_exact_legacy_id_repeat_fails_later_row(self, client, admin, people, isolated_storage):
        first = dict(VALID_ROW, **{"Task ID": "LEG-701", "Task Title": "Inspect relay"})
        repeat = dict(VALID_ROW, **{"Task ID": "LEG-701", "Task Title": "Inspect relay",
                                    "% Complete": "", "Attachment / Folder Link": ""})
        job = upload(client, [first, repeat]).json()
        assert job["failed_rows"] == 1
        report = client.get(f"/api/v1/imports/{job['id']}/report").json()
        later = next(r for r in report["rows"] if r["row_number"] == 3)
        assert later["status"] == "failed"
        assert any("Duplicate within file" in e for e in later["errors"])
        assert later["normalized"] is None

    def test_likely_in_file_repeat_needs_review(self, client, admin, people, isolated_storage):
        first = dict(VALID_ROW, **{"Task ID": "LEG-801", "Task Title": "Inspect relay",
                                   "% Complete": "", "Attachment / Folder Link": ""})
        repeat = dict(VALID_ROW, **{"Task ID": "LEG-802", "Task Title": "inspect  relay",
                                    "% Complete": "", "Attachment / Folder Link": ""})
        job = upload(client, [first, repeat]).json()
        report = client.get(f"/api/v1/imports/{job['id']}/report").json()
        later = next(r for r in report["rows"] if r["row_number"] == 3)
        assert later["status"] == "warning"
        kinds = {d["kind"] for d in later["duplicates"]}
        assert "likely_in_file" in kinds
        assert later["normalized"]["duplicate_review"] is True

    def test_in_file_duplicates_excluded_from_commit(self, test_db, client, admin, people, isolated_storage):
        first = dict(VALID_ROW, **{"Task ID": "LEG-901", "Task Title": "Inspect relay",
                                   "% Complete": "", "Attachment / Folder Link": ""})
        repeat = dict(VALID_ROW, **{"Task ID": "LEG-902", "Task Title": "Inspect relay",
                                    "% Complete": "", "Attachment / Folder Link": ""})
        job, response = TestCommit()._upload_and_commit(client, [first, repeat])
        assert response.status_code == 200
        assert response.json()["committed_rows"] == 1
        titles = test_db.scalars(select(Task.title).where(Task.title == "Inspect relay")).all()
        assert len(titles) == 1
