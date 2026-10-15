# DecOps Restore Test Report - Phase 9

**Date**: 2026-10-15. **Objective** (spec Phase 9): "Test backup restoration."

## 1. Procedure

Script: `scripts/restore_test_phase9.py` (committed). Steps executed against the
live development database (`backend/decops.db`, SQLite - the sandbox stand-in
for the production PostgreSQL instance):

1. **Online backup** taken with `sqlite3.Connection.backup()` - a consistent,
   page-level copy that is safe while the API is running (equivalent to
   `pg_dump` for the production engine).
2. **Pre-incident state recorded**: tasks=17, users=5, audit_events=145,
   import_jobs=2.
3. **Data-loss incident simulated**: a task row's title was overwritten in the
   live database (verified: 1 damaged row).
4. **Restore**: the backup artifact was restored onto a fresh database file
   (the SQLite analogue of `pg_restore --clean`; full PostgreSQL procedure in
   `docs/runbook.md` §4).
5. **Verification** on the restored database.

## 2. Results

| Check | Expected | Actual | Verdict |
|---|---|---|---|
| `PRAGMA integrity_check` | ok | ok | PASS |
| Task count after restore | 17 | 17 | PASS |
| User count after restore | 5 | 5 | PASS |
| Audit event count after restore | 145 | 145 | PASS |
| Import job count after restore | 2 | 2 | PASS |
| Damaged row absent after restore | 0 | 0 | PASS (damage reverted) |
| Alembic migration head | `5ea882cfbadf` | `5ea882cfbadf` | PASS |
| `PRAGMA foreign_key_check` | clean | clean | PASS |

**RESTORE TEST PASSED.**

## 3. Interpretation

- Backups taken with the online-backup API are self-consistent and fully
  restorable: row counts reconcile exactly, the incident damage is absent, the
  schema is at the expected migration head, and no referential-integrity
  violations exist after restore.
- Because audit trails are ordinary (append-only) tables inside the database,
  restoring a backup also restores the audit history up to the backup point -
  consistent with the audit design (no external state to lose).
- Application-level state outside the database is limited to two directories
  (`backend/var/attachments`, `backend/var/imports`) - the runbook requires
  backing these up alongside the database so restored task references remain
  downloadable.

## 4. Cadence for production

- Nightly automated database backup + attachment/import directory sync,
  with a monthly restore drill using this same test procedure (adapted to
  `pg_restore`), per `docs/runbook.md` §4.
