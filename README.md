# DecOps - Operations Management System (Interdec)

Internal task and workflow management system. This repository currently contains the
**Phase 2 (Application Foundation)**, **Phase 3 (Identity & Authorization)**,
**Phase 4 (Task Management)**, **Phase 5 (Workflow Engine)**, **Phase 6
(Collaboration & Notifications)**, **Phase 7 (Dashboards & Reporting)**, and
**Phase 8 (CSV Migration)**, and **Phase 9 (Hardening & UAT)**
releases from the approved implementation plan -
running frontend + backend, database migrations, secure authentication, RBAC,
user/department administration, a task access policy engine, full task management
(register, detail, lifecycle transitions, assignments, access grants, activity
history), the workflow engine (stages, milestones, subtasks, dependencies, progress
calculation, Gantt timeline, workflow editor), task comments and private attachments,
an in-app notification center backed by a transactional outbox with retry-safe
delivery, a collapsible sidebar with a mobile drawer layout, personal and
management dashboards, a department workspace, authorized reporting with CSV
exports, a CSV import center (column mapping, validation, duplicate detection,
retry-safe commits, reconciliation reports), audit logging, structured error
handling, security hardening (response headers, hardened session hygiene),
Phase 9 test reports (security, performance, restore) with a production
runbook, and an automated test suite (341 tests).

## Stack (pinned per spec)

| Layer     | Technology                                                        |
|-----------|-------------------------------------------------------------------|
| Frontend | Nuxt 4 (Vue 3, TypeScript, Tailwind CSS 4) - port **3000** |
| Backend | FastAPI (Python 3.12, Pydantic v2, SQLAlchemy 2.1) - port **8000**|
| Database  | PostgreSQL (production) / SQLite (local sandbox dev)              |
| Migrations| Alembic                                                           |

The Nuxt server proxies `/api/**` to the FastAPI backend, so the browser only ever
talks to one origin and session cookies remain first-party HttpOnly.

## Repository layout

```
├── nuxt.config.ts          # Nuxt config incl. /api proxy → :8000
├── app/                    # Nuxt app (pages, components, composables, middleware)
│   ├── pages/login.vue     # Authentication (MOD-001)
│   ├── pages/index.vue     # Dashboard shell (MOD-007 placeholder)
│   ├── pages/tasks/index.vue   # Task register (MOD-003, Phase 4)
│   ├── pages/tasks/[id].vue    # Task detail: summary, transitions, assignments,
│   │                           #   departments, access grants, activity timeline
│   ├── pages/admin/users.vue       # User administration (MOD-002, Phase 3)
│   ├── pages/admin/departments.vue # Department management (MOD-002, Phase 3)
│   ├── pages/imports/index.vue # CSV import center (Phase 8): upload, mapping,
│   │                           #   validation report, commit, reconciliation download
│   ├── components/     # AppSidebarNav (collapsible rail), AppNotifications
│   │                   #   (bell + notification center), TaskComments,
│   │                   #   TaskAttachments, WorkflowPanel, WorkflowGantt
├── backend/
│   ├── app/
│   │   ├── core/           # Settings, security, logging, error envelope
│   │   ├── db/             # Engine/session, base, portable types (UTCDateTime, JSON)
│   │   ├── models/         # users, sessions, RBAC, departments, audit_events,
│   │   │                   #   tasks + assignments/grants/activities (Phase 4),
│   │   │                   #   comments, attachments, notifications,
│   │   │                   #   notification_preferences, outbox_events (Phase 6)
│   │   ├── domain/         # Task lifecycle state machine, access policy engine
│   │   │                   #   (grant levels), assignment authorization,
│   │   │                   #   workflow/progress rules, notification rules
│   │   │                   #   (event catalog, subject redaction, backoff),
│   │   │                   #   csv_import rules (mapping tables, user resolution,
│   │   │                   #   duplicate detection, row validation)
│   │   ├── api/v1/         # /api/v1 routers: auth, users, departments, roles, tasks,
│   │   │                   #   workflow, collaboration (comments/attachments),
│   │   │                   #   notifications, dashboards, reports, imports, health
│   │   ├── services/       # auth, audit, user admin, department, task, workflow,
│   │   │                   #   collaboration, notification (outbox producer +
│   │   │                   #   delivery), email_sender, outbox_worker,
│   │   │                   #   import (staged pipeline: validate → report →
│   │   │                   #   batched retry-safe commit)
│   │   └── seeds/          # Idempotent RBAC matrix + admin seed
│   ├── alembic/            # Migrations (foundation, Phase 4, Phase 5, Phase 6, Phase 8)
│   └── tests/              # Pytest: auth, authorization, transitions, audit,
│   │                       #   access policy, assignment policy, cross-task isolation,
│   │                       #   task CRUD/transitions/assignments/grants, workflow
│   │                       #   domain/API, comments/attachments privacy,
│   │                       #   notifications/outbox/retry/sweep/email,
│   │                       #   CSV import pipeline + import center API (318 tests)
└── spec_full.json          # Full approved requirements document
```

## Running locally

Backend (from `backend/`):

```bash
uv sync                                   # install deps into .venv
uv run alembic upgrade head               # apply migrations
uv run python -m app.seeds.seed           # seed roles + admin (idempotent)
uv run uvicorn app.main:app --port 8000   # start API
```

Frontend (from repo root):

```bash
npm install
npm run dev                               # http://localhost:3000
```

Default seed administrator (override via env, see `backend/.env.example`):

```
admin@interdec.com / DecOps!2026
```

## Environment configuration

Backend settings are env-driven with the `DECOPS_` prefix (see
`backend/app/core/config.py`). Switching to PostgreSQL in any real environment:

```
DECOPS_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/decops
DECOPS_SECURE_COOKIES=true
DECOPS_ENVIRONMENT=production
DECOPS_SESSION_SECRET_KEY=<generated secret>
```

## API surface (Phase 2 - Phase 8)

- `POST /api/v1/auth/login` - session login (Argon2id, throttling, audited)
- `POST /api/v1/auth/logout` - session revocation (immediate)
- `GET /api/v1/auth/me` - profile, global roles, permission codes
- `GET /api/v1/users` - admin-only, paginated directory (filter by q/status)
- `POST /api/v1/users` - create employee (audited)
- `GET/PATCH /api/v1/users/{id}` - profile detail / update (audited)
- `POST /api/v1/users/{id}/status` - activate/deactivate (revokes sessions, audited)
- `POST /api/v1/users/{id}/roles` - assign global role (`roles.assign`, audited)
- `DELETE /api/v1/users/{id}/roles/{role_id}` - revoke role (audited)
- `GET /api/v1/departments` - list with member counts
- `POST /api/v1/departments` - create (optional lead → lead membership, audited)
- `GET/PATCH /api/v1/departments/{id}` - detail incl. memberships / update (audited)
- `POST /api/v1/departments/{id}/members` - assign employee (audited)
- `DELETE /api/v1/departments/{id}/members/{user_id}` - remove employee (audited)
- `GET /api/v1/roles`, `GET /api/v1/roles/permissions` - RBAC catalogue
- `GET /api/v1/tasks` - authorization-filtered register (status/priority/q/department)
- `POST /api/v1/tasks` - create with valid access policy (tasks.create, audited)
- `GET /api/v1/tasks/{id}` - detail (engine VIEW; 404 on denial)
- `PATCH /api/v1/tasks/{id}` - permitted fields, optimistic concurrency (AC-18)
- `POST /api/v1/tasks/{id}/transition` - validated lifecycle transitions with
  reason/explanation enforcement and per-target operation authorization
- `GET /api/v1/tasks/{id}/transition-options` - allowed next statuses for the UI
- `POST/DELETE /api/v1/tasks/{id}/assignments[/{assignment_id}]` - accountable/supporting
  PM assignment (DEC-02, assigning user recorded, audited)
- `POST /api/v1/tasks/{id}/departments` - link participating department
- `POST/DELETE /api/v1/tasks/{id}/access-grants[/{grant_id}]` - view/operate/manage/denied
  grants; immediate revocation; audited (engine CHANGE_VISIBILITY)
- `GET /api/v1/tasks/{id}/activity` - task activity timeline (AC-12)
- `GET /api/v1/dashboard/summary` - personal stats, upcoming deadlines, blocked
  work, recent authorized activity; management overview block for
  `dashboards.view` holders (all aggregates engine-authorized)
- `GET /api/v1/dashboard/my-tasks` - assigned/accountable/all scopes, paginated
- `GET /api/v1/dashboard/overdue`, `GET /api/v1/dashboard/blocked` - filtered views
- `GET /api/v1/reports/task-completion` - weekly created/completed trend, milestone
  progress, blocker analysis (`reports.view`)
- `GET /api/v1/reports/department-workload` - per-department active/overdue/blocked/
  completed counts + open assignments (`reports.view` all ·
  `reports.department.view` own departments)
- `GET /api/v1/reports/departments/{id}/workspace` - department workspace payload
  (authorized tasks, workload, upcoming, blocked, team assignments)
- `POST /api/v1/reports/exports` - authorized CSV exports (`exports.approved`):
  task register / department workload / completion trend; rows re-pass the access
  engine, cells are formula-injection sanitized, every export is audited
- `POST /api/v1/imports/csv` - upload + validate a legacy CSV (`imports.manage`):
  file type/size/encoding/header checks, auto column mapping, full row validation
- `GET /api/v1/imports` - import job history with reconciliation counters
  (`imports.view` or `imports.manage`)
- `GET /api/v1/imports/{id}` - job detail; `GET .../report` - row-level validation
  report (errors, notices, duplicates, normalized preview)
- `GET /api/v1/imports/{id}/report/download` - reconciliation summary CSV
- `PATCH /api/v1/imports/{id}` - operator-approved mapping/options update + revalidate
- `POST /api/v1/imports/{id}/commit` - batched, retry-safe commit of validated rows
  (duplicates/failed rows excluded and reported; `import.committed` audited)
- `GET /api/v1/health` - liveness + database check
- OpenAPI docs at `/api/docs` (non-production)

## Security controls shipped (spec §security)

- Argon2id password hashing; opaque session tokens stored only as SHA-256 hashes
- HttpOnly + SameSite=Lax cookies; `secure` flag configurable for HTTPS deployments
- Login throttling with temporary lockout; account deactivation enforcement
- Non-enumerating authentication errors (unknown user ≡ wrong password)
- 404 (not 403) for protected resources to avoid confirming existence
- Append-only audit events for login/logout/failures; sensitive keys redacted
- Structured JSON logs with request ids; consistent error envelope
- Optimistic-concurrency `version` columns prepared for task editing (AC-18)

## Test suite

```bash
cd backend && uv run pytest   # 341 tests: transitions, auth, authorization, audit,
                              #   access policy, assignment policy, cross-task isolation,
                              #   task CRUD/edits/transitions/assignments/grants/activity,
                              #   workflow state machines, dependency cycles, sequential/
                              #   parallel gating, completion rules, progress calculation,
                              #   workflow API authz + optimistic concurrency,
                              #   dashboards/reports reconciliation + leak prevention,
                              #   authorized CSV exports (filters, sanitization, audit),
                              #   CSV migration (mapping tables, user resolution, duplicates,
                              #   row validation, retry-safe commit, access preservation)
```

## Task access policy engine (Phase 3 + Phase 4 deliverable)

`backend/app/domain/access_policy.py` implements the spec's four visibility modes
(`private`, `participants`, `department_scoped`, `custom`) as pure, stateless logic:

- Every task carries an explicit, self-contained policy (mode + grants + denials)
- Precedence: explicit denial > permitted admin > explicit grant > creator > scope
- **Grant levels (Phase 4)**: `view` (read/comment), `operate` (default - update,
  coordinate), `manage` (administer); visibility changes always additionally
  require `tasks.update_assigned`
- Grants are embedded per policy, so access to one task can never leak to another
  (proven by `tests/test_isolation.py` and API-level tests - the Phase 3 exit criterion)
- Revocation is structural: the engine is re-evaluated against fresh actor state on
  every request, so permission/role/membership changes apply immediately
- `assignment_policy.py` enforces one accountable PM (DEC-02), active-assignee rules,
  and department-scoped assignment authorization; the assigning user is recorded
- `task_lifecycle.py` + `task_service.transition_task` enforce the spec transition
  matrix: backend-validated transitions, reason-required cancellations/reopenings,
  blocker explanations, terminal timestamps, and per-target operation authorization

## Task management (Phase 4 deliverables)

- **Task register** (`/tasks`): all engine-authorized tasks with number, title,
  accountable PM, departments, priority, status, progress, due date; filters and
  pagination; overdue highlighting
- **Task detail** (`/tasks/{id}`): summary + inline editing (AC-18 optimistic
  concurrency), transition actions with reason capture, assignments (DEC-02
  replacement), participating departments, access grants with levels, and the
  full activity timeline
- **Task numbers**: `TSK-YYYY-NNNN`, unique and sequential
- **Audit + activity**: every create/edit/transition/assignment/grant writes both
  an admin audit event and a user-facing task activity entry

## Workflow engine (Phase 5 deliverables)

`backend/app/domain/workflow.py` + `backend/app/domain/progress.py` implement the
spec's workflow rules as pure, exhaustively unit-tested logic:

- **Structure**: Task → Stage → Milestone/Subtask (subtasks may nest under
  milestones); stages carry sequence numbers, execution modes, weights, progress
  basis, and stage-specific deadlines
- **Execution modes**: sequential stages become actionable only when every
  earlier stage is completed/cancelled; parallel stages may run simultaneously;
  mixed workflows combine both (AC-05)
- **Dependencies**: work items connect within or across stages; self edges,
  duplicates, and **circular dependencies are rejected** (DFS reachability);
  blocked items cannot start until predecessors complete (cancelled
  predecessors satisfy the edge - an audited scope decision)
- **Completion rules**: a milestone with required subtasks cannot be completed
  by hand - it auto-completes when the last required subtask completes (and
  reopens if a subtask reopens); a stage can complete only when all required,
  non-cancelled items are done
- **Progress calculation (AC-06)**: weighted stages × required items; optional
  and cancelled items excluded; subtasks roll up into their milestone (no double
  counting); manual vs calculated modes are explicit - switching is audited and
  manual percent entry is rejected while calculated
- **History**: completed items keep `completed_at` + activity + audit records;
  every workflow mutation is audited AND shown on the task timeline
- **Concurrency**: work-item edits carry optimistic version checks (AC-18)
- **API**: `/tasks/{id}/workflow` (tree + blockers + progress method),
  stage/item CRUD + transitions + assign, dependencies, progress mode,
  `/workflow-templates` (admin)
- **UI**: Workflow editor on the task detail page (stages, items, assignments,
  dependencies, reason modals for audited transitions) and a **Gantt timeline**
  with stage bars, milestone diamonds, dependency curves, and a today marker

## Collaboration & notifications (Phase 6 deliverables)

- **Comments** (`TaskComments.vue` + `/tasks/{id}/comments`): task-scoped
  threads (optionally bound to a work item), soft delete by the author or
  task managers, activity entries, and full access-engine enforcement -
  a user without VIEW on the task gets the same 404 as everywhere else
- **Private attachments** (`TaskAttachments.vue` + `/tasks/{id}/attachments`):
  multipart upload to server-side storage (paths never exposed), sha256
  checksum, size/extension restrictions, `scan_status` field for future AV
  integration, authorization-checked download streaming, uploader/manager
  soft delete - cross-task download is structurally impossible (mandatory
  security scenario tested)
- **In-app notification center** (`AppNotifications.vue` + `/notifications`):
  unread badge with 30 s polling, panel with relative timestamps, click-through
  to the resource, mark-read / mark-all-read; recipients always re-resolved and
  authorization **re-checked at delivery time**, so revoked access never
  receives disclosure (spec mandatory test scenario)
- **Transactional outbox** (`outbox_events` + `notification_service` +
  `outbox_worker.py`): business mutations enqueue delivery events in the SAME
  database transaction (a rollback removes the event), a background worker
  delivers with per-event commits, idempotent replay (unique per event +
  recipient), exponential backoff retries for transient failures, and recorded
  permanent failures - "notification processing is retry-safe" (exit criteria)
- **Event coverage**: task assigned, supporting PM added, task blocked, blocker
  resolved, work item completed, milestone completed, task submitted for
  review, review rejected, task completed, task reopened, visibility changed,
  access granted/revoked, deadline approaching / overdue (worker sweep with a
  per-window dedup)
- **Optional email channel** (`email_sender.py`, disabled by default): SMTP
  delivery respecting per-user preferences; subjects for confidential tasks
  (private/custom visibility) use the task **number only**, never the title
- **Per-user preferences** (`/notifications/preferences`): in-app and email
  switches per event type, honored by the delivery pipeline

## Dashboards & reporting (Phase 7 deliverables)

- **Authorization-aware aggregation core**: every dashboard/report/export number
  is computed from one `visible_tasks()` source that re-evaluates the task
  access engine (fresh actor context + per-task policy) - totals reconcile
  with the authorized register by construction and restricted tasks cannot
  leak through reports (spec exit criteria)
- **Personal dashboard** (`/`): assigned/accountable/overdue/blocked stat
  cards, due-soon indicator, upcoming deadlines (30-day window), blocked
  work, and recent authorized activity across visible tasks
- **Management overview**: `dashboards.view`-gated block with visible totals,
  active/overdue/blocked, completion rate, and weekly completions
- **My Tasks** (`/my-tasks`): assigned / accountable / all scope tabs,
  priority + status badges, progress bars, due dates with overdue flags,
  pagination
- **Department workspace** (`/departments`, `/departments/{id}`): workload
  cards per department, authorized departmental tasks, upcoming deadlines,
  blocked/overdue panels, and team assignments (leads are scoped to their own
  departments; management sees all - task contents stay engine-filtered)
- **Reports** (`/reports`): 12-week created/completed SVG trend chart, cycle
  time, status breakdown, milestone progress, blocker analysis by priority
  and department, department workload table
- **Authorized CSV exports**: `exports.approved`-gated (Read-Only Auditor per
  the spec RBAC matrix), register filters supported, Content-Disposition
  download, formula-injection sanitization, `report.exported` audit events
- **Fixed en route**: `visibility_mode` is now PATCHable through the task API
  (service gate existed since Phase 6; the request schema never exposed it) -
  guarded by the CHANGE_VISIBILITY engine operation with regression tests

## CSV migration & import center (Phase 8 deliverables)

- **Staged pipeline** (spec `spreadsheet_migration.import_pipeline`): upload →
  validate (file type / size / encoding / header structure) → auto column
  mapping with operator overrides → preview of normalized rows → resolve
  people against the directory → duplicate detection → row-level validation
  report → batched commit → reconciliation summary download
- **Approved mapping tables**: legacy statuses ("In Progress", "On Hold",
  "Done", …) and priorities ("P1", "Urgent", …) map onto the DecOps enum;
  unmapped values FAIL the row and are reported - nothing is invented or
  silently defaulted (dates support ISO / day-first / month-first with an
  operator-approved interpretation)
- **User resolution without guessing**: exact email → exact employee code →
  unique full-name match; ambiguous names match multiple users and FAIL the
  row for manual resolution (spec: never invent a user mapping); inactive
  users are rejected as assignees
- **Duplicate detection**: exact `task_number` / `legacy_external_id`
  identifier matches (commit-blocking), configurable title+due-date ("likely")
  and title-only ("possible") rules, plus intra-file repeats - duplicates are
  excluded from commit and reported, never re-imported
- **Legacy data policy honored**: historical `Date Created` timestamps and
  `Completion Date` are preserved, supplied percentages are imported with a
  "reconcile against workflow calculation" flag, dependency descriptions and
  attachment links are stored verbatim as untrusted references (never
  fetched), and a `task.imported` activity records real provenance (import
  actor, file, row, source ID) - no historical audit events are fabricated
- **Retry-safe commits**: rows commit in controlled batches together with the
  job counters; a mid-run failure keeps committed rows and the job can be
  re-committed - already-imported legacy identifiers are recognized and
  skipped (`already_committed_rows`), never duplicated; a committed job is
  immutable (409 on PATCH/second commit)
- **Access preservation**: imports cannot grant unauthorized access - tasks
  get the operator-approved initial visibility policy, assignments are limited
  to the accountable/supporting PMs from the sheet, no access grants are
  created, and post-commit authorization tests verify outsiders still get 404
- **Import center UI** (`/imports`, `imports.manage`/`imports.view` gated -
  deliberately NOT granted to System Administration per the spec restriction
  on technical administration): upload button, job history with counters,
  per-row validation report with error/notice/duplicate chips, mapping +
  options editor with revalidation, commit with confirmation, and
  `summary.csv` reconciliation download

## Application shell (collapsible sidebar + mobile)

- **Desktop**: fixed collapsible sidebar (full and icon rail) with active-route
  indicator, persisted per browser via `localStorage`
- **Mobile**: off-canvas drawer behind a hamburger button with backdrop,
  auto-close on navigation, and a responsive single-column content layout
- Header hosts the theme toggle, notification bell (unread badge), and the
  account menu (identity, roles, My Tasks, Settings, sign out)
- Hexagon "D" brand mark as the product logo (sidebar, login, PDF header, favicon)

## Settings & theming (post-launch evolution)

- **Dark / light / system modes** with a pre-paint no-flash script, theme
  dropdown in the header, and full dark tokens across every screen
- **Appearance settings** (Settings > Appearance): theme mode, six accent
  palettes (emerald, blue, violet, rose, amber, slate), and four interface
  font stacks; saved per user on the server and per device in localStorage
- **Organization settings** (Settings > Organization): org name and tagline
  shown in the PDF header and the interface footer
- **Roles & permissions editor** (Settings > Roles & Permissions): create,
  edit, and delete custom roles with a grouped, searchable permission matrix;
  system roles stay read-only to protect the approved spec matrix; all changes
  audited (`role.created` / `role.updated` / `role.deleted`)
- **Users & access** (Settings > Users & Access): grant login with a generated
  initial password, assign or revoke roles, and reactivate or revoke accounts
- **Customizable PDF design** (Settings > PDF Exports, WeasyPrint): paper size,
  orientation, accent color, document font, body size, cover page, header logo
  and org name, footer text, page numbers, and table style, with a live sketch
  plus a sample-data preview PDF before saving
- **Dashboard charts**: dependency-free SVG visualizations over the authorized
  task set: weekly created-vs-completed trend, tasks-by-status donut, and
  workload by department
- **PDF exports** on the Reports page for the task register, completion trend,
  and department workload; every PDF uses the saved design and the same
  engine-authorized rows as CSV exports (audited)

## Decisions defaulted (from spec §decisions_to_confirm_with_interdec)

- DEC-02: one accountable PM, multiple supporting PMs (modelled in schema)
- DEC-11: timestamps stored in UTC (`UTCDateTime`), rendered client-side
- DEC-12: local credential management for now; `authentication_reference`
  column is SSO-ready
- DEC-13: in-app notifications delivered; the email channel ships disabled
  ("Email, if approved" per spec) and is configurable via `DECOPS_EMAIL_*`
  settings
- These remain subject to Interdec sign-off per the spec.

## Production launch (Phase 10 deliverables)

- **Launch orchestrator** (`scripts/launch_phase10.py`): idempotent, audited
  launch drill - configuration/DB preflight (rejects default secrets, checks
  migrations + RBAC seed + initial admin), approved-account provisioning from
  `docs/launch/accounts_manifest.csv` (9 staff across all 9 system roles,
  audited `user.created`, credentials file chmod 600 and stable across re-runs),
  validated task-register import through the real Phase 8 pipeline
  (retry-safe: fully-imported registers are detected and skipped), and a
  per-role HTTP smoke matrix (26 probes incl. negative RBAC assertions).
- **Early-usage monitor** (`scripts/monitor_phase10.py`): health, adoption
  (logins/distinct users), register health, outbox backlog, failed-login
  burst alerting - JSON snapshots retained under `backend/var/monitoring/`.
- **Production launcher** (`scripts/start_prod.sh`): migrations → seed →
  launch drill → frontend build → API + Nuxt servers with enforced production
  posture (secret/cookie/db env required).
- **Documentation set**: `docs/user-guide.md` (end users),
  `docs/admin-guide.md` (administrators), `docs/support-procedures.md`
  (support tiers, incident playbook, feedback intake & prioritization),
  `docs/reports/phase10_launch_report.md` (launch drill record + exit
  criteria assessment), `docs/launch/` (accounts manifest, validated
  register, feedback log template).
- **Launch guard tests** (`tests/test_launch.py`): credential-source
  stability (0600 file), smoke-matrix coverage of every system role,
  retry-safe register pre-check, launch-asset well-formedness.
- Interdec's formal rollout acceptance remains the final sign-off item (see
  the launch report §6).

## Roadmap

All ten phases of the approved `implementation_phases` in `spec_full.json`
are shipped. Post-launch evolution is driven by the feedback triage loop
(`docs/support-procedures.md` §4).

## Hardening & UAT (Phase 9 deliverables)

- **Security test report** (`docs/reports/phase9_security_report.md`): 22-point
  security matrix verified by the new `tests/test_hardening.py` suite -
  security headers, session/cookie hygiene, unauthenticated endpoint matrix,
  IDOR/privilege-escalation probes, mass-assignment robustness, and the audit
  coverage matrix. Security headers middleware (`nosniff`, `DENY`, `no-referrer`,
  restrictive CSP, `no-store`, conditional HSTS) shipped in this phase.
- **Performance test report** (`docs/reports/phase9_performance_report.md`):
  benchmark harness (`scripts/bench_phase9.py`) measuring p50/p95 latency and
  exact SQL statement counts at 300 tasks - all endpoints p95 < 140 ms with
  flat query counts (no N+1; verified empirically via A/B).
- **Restore test report** (`docs/reports/phase9_restore_report.md`): online
  backup → simulated data-loss incident → restore → integrity/reconciliation/
  migration-state checks all pass.
- **UAT sign-off** (`docs/reports/phase9_uat_signoff.md`): persona journeys
  (Management, Lead, Auditor, Administrator) executed through the real UI;
  formal approval recorded as conditional pending Interdec.
- **Production runbook** (`docs/runbook.md`): first deployment, migrations and
  seeds, multi-worker notes (outbox worker), reverse proxy/TLS, backup &
  restore procedures, monitoring, incident response, pre-launch checklist.
