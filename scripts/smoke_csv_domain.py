"""Smoke check for csv_import domain logic (dev-time, not part of suite)."""
import sys
sys.path.insert(0, "/home/z/my-project/backend")

from app.domain import csv_import as ci

directory = ci.UserDirectory(users=[
    ci.DirectoryUser("u1", "Ann Chen", "ann@interdec.com", "INT-1", True),
    ci.DirectoryUser("u2", "Bob Ray", "bob@interdec.com", "INT-2", True),
    ci.DirectoryUser("u3", "Bob Ray", "bob2@interdec.com", "INT-3", True),
    ci.DirectoryUser("u4", "Old Guy", "old@interdec.com", "INT-4", False),
])

# auto mapping
headers = list(ci.SOURCE_COLUMNS)
mapping = ci.auto_map_headers(headers)
assert all(mapping[h] == t for h, t in ci.DEFAULT_COLUMN_MAPPING.items()), mapping

# status mapping
assert ci.normalize_status("In Progress") == "in_progress"
assert ci.normalize_status("DONE") == "completed"
assert ci.normalize_status("") == "open"
try:
    ci.normalize_status("weird-state")
    raise SystemExit("should fail")
except ci.RowError:
    pass

# percent
assert ci.normalize_percent("35%") == (35, True)
assert ci.normalize_percent("0.35") == (35, True)
assert ci.normalize_percent("") == (0, False)
try:
    ci.normalize_percent("140")
    raise SystemExit("should fail")
except ci.RowError:
    pass

# dates
assert ci.parse_date("14/03/2025").isoformat() == "2025-03-14"
assert ci.parse_date("2025-03-14").isoformat() == "2025-03-14"
assert ci.parse_date("03/14/2025", day_first=False).isoformat() == "2025-03-14"

# people
assert ci.split_people("Ann Chen; Bob Ray") == ["Ann Chen", "Bob Ray"]
assert ci.split_people("Ann Chen, Bob Ray") == ["Ann Chen", "Bob Ray"]

# resolution
u, p = directory.resolve("ann@interdec.com")
assert u and u.user_id == "u1" and not p
u, p = directory.resolve("Bob Ray")
assert u is None and "Ambiguous" in p
u, p = directory.resolve("old@interdec.com")
assert u is None and "not active" in p
u, p = directory.resolve("Nobody")
assert u is None and "does not match" in p

# duplicates
idx = ci.DuplicateIndex([
    ci.ExistingTaskRef("t1", "TSK-2026-0001", "Fix the pump", "2025-04-01", "LEG-9"),
], match_title_only=False)
assert idx.find("LEG-9", "Other", None)[0].kind == "exact_legacy_id"
assert idx.find("TSK-2026-0001", "Other", None)[0].kind == "exact_task_number"
assert idx.find(None, "fix  the Pump", None) == []  # title-only not enabled
idx2 = ci.DuplicateIndex([
    ci.ExistingTaskRef("t1", "TSK-2026-0001", "Fix the pump", "2025-04-01"),
], match_title_only=True)
m = idx2.find(None, "Fix the pump", __import__("datetime").date(2025, 4, 1))
assert m and m[0].kind == "likely"

# full row validation
row = {
    "Task ID": "LEG-77", "Date Created": "01/02/2025", "Task Title": "  Replace   belt ",
    "Task Description": "conveyor belt", "Priority": "P1", "Accountable PM": "Ann Chen",
    "Supporting PM(s)": "Bob Ray; Bob Ray; Old Guy", "Assigned By": "Mystery Person",
    "Start Date": "02/02/2025", "Due Date": "03/05/2025", "Status": "On Hold",
    "% Complete": "40", "Last Updated": "", "Next Follow-up Date": "",
    "Dependency / Blocker": "Waiting on pump part", "Attachment / Folder Link": "https://drive.example/f/xyz",
    "Completion Date": "",
}
rep = ci.validate_row(row, row_number=2, mapping=mapping, directory=directory, duplicates=idx)
# Ambiguous "Bob Ray" + inactive "Old Guy" => row must FAIL (never invented).
assert rep.status == "failed", (rep.status, rep.errors)
assert any("Ambiguous" in e for e in rep.errors)
assert any("not active" in e for e in rep.errors)

# Clean supporting PM list => warning row (percent reconciliation + external link)
row2 = {**row, "Supporting PM(s)": "bob@interdec.com"}
rep2 = ci.validate_row(row2, row_number=3, mapping=mapping, directory=directory, duplicates=idx)
assert rep2.status == "warning", (rep2.status, rep2.errors)
n = rep2.normalized
assert n.title == "Replace belt"
assert n.priority == "high" and n.status == "blocked" and n.percent_complete == 40
assert n.accountable_pm_id == "u1"
assert n.supporting_pm_ids == ["u2"]
assert n.due_date == "2025-05-03"  # day-first interpretation of 03/05/2025
assert any("untrusted reference" in nt for nt in rep2.notices)
assert rep2.normalized.percent_requires_reconciliation is True
