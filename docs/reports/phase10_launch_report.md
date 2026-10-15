# Phase 10 Launch Report - Production Launch (DecOps)

**Date:** 2026-10-15 · **Release:** main @ c565803 (Phase 9 baseline) + Phase 10 launch tooling
**Environment:** sandbox standing in for production (SQLite dev DB; production
targets PostgreSQL per runbook) · **Orchestrator:** `scripts/launch_phase10.py`

## 1. Scope executed

Phase 10 objectives → implemented as a repeatable, audited launch drill:

| Objective | Implementation | Result |
|---|---|---|
| Deploy the production environment | `scripts/start_prod.sh` (migrations → seed → launch drill → build → API + Nuxt servers); production build validated (`bun run build`, 2.5 MB output); hardened posture enforced by preflight (`Secure` cookies/HSTS, OpenAPI off, secrets required) | ✅ drill validated; build clean |
| Create approved user accounts | `docs/launch/accounts_manifest.csv` (9 approved staff across all 9 system roles) provisioned via `user_admin_service` with audited `user.created` events, role grants, and Operations department memberships; credentials generated to `backend/var/launch_credentials.csv` (chmod 600, rotate-at-first-login policy) | ✅ 9/9 provisioned (idempotent - re-runs skip) |
| Import the validated task register | `docs/launch/task_register.csv` (8 legacy rows, exact 17-column Interdec format) through the real Phase 8 pipeline: auto-mapping → validation → batched commit. First run: 8 rows committed (3 clean, 5 with reconciliation warnings - legacy date/status vocabulary), 0 failed. Re-run correctly skipped: all 8 legacy IDs present (`already_imported`) - retry-safe | ✅ 8/8 tasks migrated |
| Train users and administrators | `docs/user-guide.md` (end-user, all modules), `docs/admin-guide.md` (roles, accounts, imports, audit, ops duties) | ✅ delivered |
| Monitor early usage | `scripts/monitor_phase10.py` - health, adoption (logins/distinct users), register health, outbox backlog, failed-login burst alerting (threshold 10/15 min), JSON snapshots retained (20) | ✅ validated live (caught the drill's own failed-login burst from earlier mis-provisioned smoke credentials; alert cleared after fix) |
| Collect and prioritize feedback | `docs/support-procedures.md` §4 - intake model + impact-based prioritization matrix; `docs/launch/feedback_log.csv` template wired into the weekly triage cadence | ✅ process live |

## 2. Preflight (launch gate)

`database_configured` PASS · `session_secret_rotated` PASS (correctly FAILED on
first run with the default secret - the guard works) · `database_reachable`
PASS · `rbac_seeded` PASS (9 system roles) · `initial_admin_present` PASS ·
`migrations_applied` PASS (head `5ea882cfbadf`). One expected WARN: the sandbox
runs `environment=development`; the production rollout sets
`DECOPS_ENVIRONMENT=production` via `start_prod.sh`.

## 3. Smoke matrix (HTTP, per role - 26 probes, all green)

| Role | Probes |
|---|---|
| Company Administrator (seed admin) | me, tasks, imports, users → 200 |
| Management | me, dashboard/summary, tasks, reports/task-completion → 200 |
| Accountable PM ×2 | me, tasks, dashboard/summary → 200 |
| Supporting PM | me, dashboard/my-tasks → 200 |
| Department Lead | me, dashboard/summary, my-tasks → 200; **departments → 404** (manage-only surface correctly blocked) |
| Department Member ×2 | me, my-tasks → 200 |
| Approver | me, tasks → 200 |
| Read-Only Auditor | me, tasks → 200; **reports/task-completion → 404, users → 404** (no `reports.view`/`users.manage` per spec matrix - negative assertions) |

Every probe used a real login + session cookie over HTTP against the running
stack; results archived in `backend/var/launch/launch_report-*.json`
(passwords excluded from reports by construction).

## 4. Early-usage snapshot (at launch)

14 users · 25 tasks (draft 1 / open 7 / in-progress 8 / blocked 2 / completed
7) · 4 import jobs (3 committed + the launch register) · outbox backlog 0 ·
audit 24 h: 63 logins, 29 logouts, 26 status changes, 25 task creations ·
monitor alerts functioning (failed-login burst detection demonstrated during
drill debugging, then cleared).

## 5. Issues found & fixed during the drill

1. **Smoke credential instability** - passwords regenerated per run caused
   401s; fixed by making `backend/var/launch_credentials.csv` the stable
   credential source across re-runs (idempotent provisioning).
2. **Smoke RBAC matrix guesses** - two probes targeted manage-only surfaces;
   converted to negative assertions (404), strengthening the test.
3. **Monitor action name** - login metric now uses the audited
   `auth.login` action.

## 6. Exit criteria assessment

- **Authorized users can perform their required workflows** - ✅ 26/26 role
  smoke probes green, including negative permission assertions (Phase 9 UAT
  walkthroughs corroborate; `phase9_uat_signoff.md`).
- **Monitoring, backup, and recovery processes are operational** - ✅ monitor
  validated live; backup/restore drill passed in Phase 9
  (`phase9_restore_report.md`); nightly backup + monthly drill scheduled in
  runbook §4.
- **Interdec accepts the production rollout** - ⏳ pending: formal acceptance
  is an Interdec decision. Package: this report + UAT sign-off + runbook +
  guides. Open item carried from Phase 9: infrastructure-level penetration
  test (outside application scope).

## 7. Handover checklist for the real rollout

1. Provision PostgreSQL + TLS reverse proxy (runbook §2).
2. Set production `DECOPS_*` env (`start_prod.sh` enforces secret/cookie posture).
3. Run `start_prod.sh` (migrations → seed → launch drill → build → serve).
4. Distribute temporary credentials via secure channel; users rotate at first login.
5. Begin daily monitor cadence + weekly feedback triage (`support-procedures.md` §6).
