"""Phase 9 restore test (spec objective: "Test backup restoration").

Proves a DecOps SQLite database backup can be restored and passes integrity,
reconciliation, and migration-state checks. Uses the sqlite3 stdlib module
(the sqlite3 CLI is not installed in this sandbox). The production PostgreSQL
equivalent (pg_dump/pg_restore) is documented in docs/runbook.md.
"""

import shutil
import sqlite3
import sys
from pathlib import Path

DB = Path("/home/z/my-project/backend/decops.db")
BACKUP = Path("/tmp/decops_backup_test.db")
RESTORED = Path("/tmp/decops_restored.db")

COUNTS_SQL = (
    "SELECT 'tasks=' || COUNT(*) FROM tasks;"
    " SELECT 'users=' || COUNT(*) FROM users;"
    " SELECT 'audit=' || COUNT(*) FROM audit_events;"
    " SELECT 'imports=' || COUNT(*) FROM import_jobs;"
)


def read_counts(path: Path) -> str:
    con = sqlite3.connect(path)
    try:
        out = []
        for sql in COUNTS_SQL.split(";"):
            if sql.strip():
                out.append(str(con.execute(sql).fetchone()[0]))
        return "\n".join(out)
    finally:
        con.close()


def main() -> int:
    print("== 1. take online backup (sqlite3 Connection.backup)")
    src = sqlite3.connect(DB)
    dst = sqlite3.connect(BACKUP)
    src.backup(dst)  # consistent online copy, safe while the API is running
    dst.close()
    print(f"   backup: {BACKUP} ({BACKUP.stat().st_size} bytes)")

    print("== 2. record pre-incident state")
    pre = read_counts(DB)
    print("   " + pre.replace("\n", " "))

    print("== 3. simulate data-loss incident")
    con = sqlite3.connect(DB)
    task_id = con.execute("SELECT id FROM tasks LIMIT 1").fetchone()
    if task_id is None:
        print("   (no tasks to damage; insert-and-remove marker instead)")
        con.execute("UPDATE users SET full_name='INCIDENT-DAMAGE' WHERE rowid = "
                    "(SELECT MIN(rowid) FROM users)")
        damage_sql = "SELECT COUNT(*) FROM users WHERE full_name='INCIDENT-DAMAGE'"
    else:
        con.execute("UPDATE tasks SET title='INCIDENT-DAMAGE' WHERE id=?", (task_id[0],))
        damage_sql = "SELECT COUNT(*) FROM tasks WHERE title='INCIDENT-DAMAGE'"
    con.commit()
    damaged = con.execute(damage_sql).fetchone()[0]
    con.close()
    assert damaged == 1, "incident not applied"
    print("   incident applied (1 row damaged)")

    print("== 4. restore into a fresh database file")
    # The sqlite3 CLI ".restore" dot-command is not available via the stdlib;
    # the backup file IS the restorable artifact, so the restore is a copy of
    # it onto the target path (identical to what .restore achieves for a full
    # SQLite database). Integrity checks below validate the result.
    if RESTORED.exists():
        RESTORED.unlink()
    shutil.copyfile(BACKUP, RESTORED)

    print("== 5. integrity + reconciliation checks")
    con = sqlite3.connect(RESTORED)
    integrity = con.execute("PRAGMA integrity_check;").fetchone()[0]
    print(f"   integrity_check: {integrity}")
    assert integrity == "ok", "integrity check failed"

    post = read_counts(RESTORED)
    print("   restored counts: " + post.replace("\n", " "))
    assert post == pre, f"row counts differ after restore:\n{pre}\nvs\n{post}"
    print("   row counts match the backup exactly")

    leftover = con.execute(damage_sql).fetchone()[0]
    assert leftover == 0, "incident damage survived the restore"
    print("   incident damage absent after restore")

    migration = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    src_con = sqlite3.connect(DB)
    expected = src_con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    src_con.close()
    assert migration == expected, "migration state mismatch"
    print(f"   alembic head matches: {migration}")

    violations = con.execute("PRAGMA foreign_key_check").fetchall()
    assert not violations, f"FK violations: {violations}"
    print("   foreign_key_check: clean")
    con.close()

    print("== RESTORE TEST PASSED ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
