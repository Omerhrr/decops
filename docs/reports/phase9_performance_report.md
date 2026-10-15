# DecOps Performance Test Report - Phase 9

**Date**: 2026-10-15. **Environment**: sandbox (SQLite, in-process TestClient),
isolated dataset: 24 users, 4 departments, 300 tasks with mixed visibility
modes, 5 import jobs.

## 1. Method

- Benchmark harness: `scripts/bench_phase9.py` (committed). It seeds a
  deterministic dataset, warms each endpoint, then measures 12 iterations of
  wall time plus the exact number of SQL statements per request (via a
  `before_cursor_execute` event listener).
- A/B verification of the authorization-loop query count was performed by
  running the same probe against the pre-change service code (git stash) and
  the current code.

## 2. Results (300 tasks, 24 users)

| Endpoint | p50 (ms) | p95 (ms) | mean (ms) | SQL statements |
|---|---:|---:|---:|---:|
| Task register (25/page) | 54.3 | 127.3 | 67.4 | 34 |
| Task register (100/page) | 56.8 | 126.1 | 73.8 | 34 |
| Personal dashboard (`/dashboard/summary`) | 59.4 | 117.6 | 70.2 | 36 |
| My tasks (`/dashboard/my-tasks`) | 54.9 | 126.8 | 67.2 | 35 |
| Completion report (`/reports/task-completion`) | 58.1 | 133.8 | 76.7 | 35 |
| Workload report (`/reports/department-workload`) | 60.3 | 132.2 | 72.4 | 37 |
| CSV import validation (1000 rows) | 87.9 | - | - | 27 |

## 3. Authorization-loop query analysis (N+1 check)

The register, dashboard, and every report re-evaluate the task access engine
per candidate task (`build_policy` reads each task's assignments and access
grants). This is the only place a per-row query amplification could occur:

- **Finding**: no N+1 exists. Both relationships are declared
  `lazy="selectin"` at the model level, so candidates always load their
  assignments/grants in a fixed pair of extra statements regardless of row
  count.
- **Empirical A/B**: `GET /tasks` issued **34 SQL statements both before and
  after** adding explicit `selectinload` options to the loop queries - flat
  query count with 300 candidates (would be ~634 statements if two lazy loads
  ran per candidate).
- **Action taken**: the explicit eager-loading was kept as defense-in-depth
  (it documents the requirement inside the query itself and guards against
  future relationship-option changes) at zero measured cost.

## 4. Observed profile

- Latency is dominated by Python-side authorization evaluation, not SQL:
  statement counts stay flat (34 - 37) as candidate volume grows, and p95 stays
  under ~135 ms across all measured endpoints.
- The heaviest single operation measured is a worst-case 1000-row CSV import
  validation where every row duplicates an already-imported legacy identifier
  (full duplicate index probe per row): ~88 ms, 27 statements.
- Sandbox cap of 2000 candidate tasks (`SANDBOX_TASK_CAP` / register
  `limit(2000)`) bounds worst-case request cost; production PostgreSQL with
  proper indexes will improve the data-access share further.

## 5. Conclusion

Performance is well within the target for an internal operations tool (all
measured endpoints p95 < 140 ms at sandbox scale, flat SQL statement counts).
No performance defects were found; one hardening measure (explicit eager
loading) was adopted as defense-in-depth. Re-run before launch with
production-scale data per the runbook (`scripts/bench_phase9.py`).
