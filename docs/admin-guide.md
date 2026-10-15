# DecOps Administrator Guide

Administrator documentation for DecOps (Interdec). Covers account
administration, role assignment, imports, audit, and the operational duties
that keep the launch healthy. Deployment, backup/restore, and infrastructure
procedures live in `docs/runbook.md`; end-user features in
`docs/user-guide.md`; incident handling in `docs/support-procedures.md`.

## 1. Roles in DecOps

DecOps ships nine system roles (fixed permission sets from the approved RBAC
matrix — see `backend/app/seeds/rbac_matrix.py`):

| Role | Typical grant | Notes |
|---|---|---|
| Company Administrator | Users, departments, imports, full task administration | Business owner of the system |
| System Administrator | Technical administration (no business content visibility) | Sees no task data by design |
| Management | Cross-department dashboards & reports | |
| Accountable PM | Owns tasks end-to-end | |
| Supporting PM | Contributes to assigned tasks | |
| Department Lead | Department workspace + lead duties | Needs a department membership |
| Department Member | Works in their department | |
| Approver | Reviews & approves | |
| Read-Only Auditor | `tasks.view_authorized`, `audit.read`, `exports.approved` | Deliberately **no** `reports.view` — auditors export data, they do not browse reports |

Roles are **global** (company scope) and combine freely; a person can be both
Accountable PM and Department Lead. Permissions are checked on every API call;
the UI only hides what the role already forbids — the API is the gate.

## 2. Account administration (Users)

*Users* (Company Administrator): create employees, assign roles, deactivate.

- **Create**: email, full name, employee code (unique), initial password
  (minimum 10 characters). Hand the initial password over through a secure
  channel (never email) and instruct the user to treat it as temporary.
- **Assign roles**: tick one or more roles at creation or later. Every change
  is written to the audit trail (`user.created`, `user.role_granted`, …) with
  your identity as actor.
- **Deactivate on departure**: deactivation (rather than deletion) preserves
  audit history and task records. Deactivation revokes access immediately:
  sessions become unusable and the user stops resolving in assignment pickers.
- **Lockouts**: five consecutive failed sign-ins lock an account for 15
  minutes (automatic). Unlock by waiting or by rotating the password.
- **Password resets**: issue a temporary password; the old one stops working.

## 3. Departments (Departments Admin)

Create departments, add/remove members, set membership roles (`lead` /
`member`). Membership drives department-scoped visibility and the
department workspace. Department membership changes are audited
(`department.member_added` / `department.member_removed`).

## 4. Task administration

- Administrators with `tasks.manage` can correct metadata, reassign, and move
  tasks through allowed transitions (reasons where required).
- **Visibility modes** on a task: `private`, `participants`,
  `department_scoped`, `custom`. Private tasks are invisible to everyone
  without a grant — including in reports and exports (404, not 403, so IDs do
  not leak).
- Assignments grants (`task.access_granted` audit action) are the mechanism to
  give a private task to a collaborator.

## 5. Imports center (CSV migration)

*Imports* (Company Administrator only — System Administration is excluded
from business content by spec):

1. **Upload** the CSV (UTF-8, ≤ 10 MB). File-level problems (wrong type,
   encoding, binary content) are rejected up front with a clear reason.
2. **Review the mapping** — headers auto-map to DecOps fields (the 17 legacy
   columns of the Interdec spreadsheet map by name). Adjust anything wrong;
   revalidation is instant.
3. **Review the row report** — per-row status:
   - *ok* — clean row;
   - *warning* — imported with a reconciliations flag (e.g. percent "0.35"
     read as 35 %, date format assumptions);
   - *failed* — not imported; the reason is stated (unmapped status value,
     bad dates, missing required field);
   - *duplicate* — flagged for review (exact matches on legacy Task ID block
     import; same-title matches are marked likely/possible).
4. **Commit** — only ok/warning rows without duplicate flags commit, in
   batches, with per-row outcomes written back into the report. Committed
   tasks keep their historical dates and show provenance (`task.imported`).
5. **Retries are safe** — re-uploading the same file never duplicates tasks:
   rows whose legacy Task ID already exists are reported, not re-imported.
6. **After commit**: download the summary CSV from the job's report for the
   migration record; `import.committed` is in the audit trail with task IDs.

## 6. Audit trail

Every security-relevant action is recorded (append-only): sign-ins and
failures, user/role/department changes, task lifecycle moves with reasons,
grants, import commits, exports. Administrators with `audit.read` (and
auditors) review it. For investigations, filter by actor, action, resource,
or time window; the `request_id` ties web requests to audit rows and server
logs (see `docs/support-procedures.md`).

## 7. Launch operations quick duties

| Duty | Cadence | Tool |
|---|---|---|
| Health + usage snapshot | Daily (first two weeks), then weekly | `python3 scripts/monitor_phase10.py` |
| Review outbox failures | On monitor alert | SQL: `outbox_events` where `status='permanent_failure'` |
| Review failed-login bursts | On monitor alert | Audit trail, `auth.login_failed` |
| Backup | Nightly | `docs/runbook.md` §4 |
| Restore drill | Monthly | `docs/runbook.md` §4 + Phase 9 drill |
| Feedback triage | Weekly | `docs/launch/feedback_log.csv` + `docs/support-procedures.md` §4 |
| Import register corrections | As raised | Imports center (retry-safe) |

## 8. Known operating constraints

- The notification outbox worker runs inside the API process; in multi-worker
  deployments enable it on exactly one worker
  (`DECOPS_OUTBOX_WORKER_ENABLED=false` elsewhere).
- Production requires PostgreSQL; SQLite exists for the sandbox only.
- Attachments and import artifacts live on local disk under `backend/var/` —
  include them in backups or downloads break after a restore.
- OpenAPI docs are disabled in production by hardening; use the repository
  schemas/tests as the API reference.
