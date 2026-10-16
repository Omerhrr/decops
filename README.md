# DecOps - Operations Management System (Interdec)

Internal task and workflow management system for Interdec. It covers the full
operational lifecycle: secure authentication and role-based access, user and
department administration, a task register with a fine-grained access policy,
a workflow engine with stages, milestones, subtasks, dependencies, and a Gantt
timeline, task comments and private attachments, an in-app notification center
backed by a transactional outbox, personal and management dashboards with
charts, authorized reporting with CSV and PDF exports, a CSV import center for
migrating legacy registers, audit logging, and a settings area for theming,
organization branding, roles, and user access provisioning.

The backend exposes a versioned REST API consumed by a Nuxt frontend. The full
approved requirements document lives in `spec_full.json`; operational
documentation lives in `docs/`.

## Stack

| Layer      | Technology                                                        |
|------------|-------------------------------------------------------------------|
| Frontend   | Nuxt 4 (Vue 3, TypeScript, Tailwind CSS 4) - port **3000**        |
| Backend    | FastAPI (Python 3.12, Pydantic v2, SQLAlchemy 2.1) - port **8000**|
| Database   | PostgreSQL (production) / SQLite (local sandbox dev)              |
| Migrations | Alembic                                                           |
| PDF engine | WeasyPrint (server-side, design configurable in Settings)         |

The Nuxt server proxies `/api/**` to the FastAPI backend, so the browser only
ever talks to one origin and session cookies remain first-party HttpOnly.

## Feature overview

### Identity, authorization, and administration

- Session authentication with Argon2id password hashing, login throttling,
  and immediate session revocation on logout or deactivation
- Global roles plus a fixed, read-only system role matrix; custom roles can be
  created and edited in Settings by permitted administrators
- User administration: create employees, assign and revoke roles, activate and
  deactivate accounts; every change is audited
- Department management with leads, members, and per-department workspaces

### Task management

- Task register with filters (status, priority, department, search) and
  pagination; task numbers are unique and sequential (`TSK-YYYY-NNNN`)
- Four visibility modes (`private`, `participants`, `department_scoped`,
  `custom`) enforced by a pure, stateless access policy; access to one task
  never leaks to another and revocation applies on the next request
- View, operate, and manage grant levels; explicit denials; per-task grants
- Lifecycle transitions validated server-side with reason-required
  cancellations and reopenings, blocker explanations, and terminal timestamps
- One accountable project manager plus supporting PMs; assigning user recorded
- Full activity timeline on every task, plus admin audit events

### Workflow engine

- Task structure: stages with sequence numbers, execution modes, weights,
  progress basis, and stage-specific deadlines; milestones and subtasks under
  stages, with subtasks able to nest under milestones
- Sequential stages unlock only when earlier stages finish; parallel stages
  run simultaneously; mixed workflows combine both
- Work-item dependencies with cycle rejection; blocked items cannot start
  before their predecessors complete
- Completion rules: required-subtask milestones auto-complete (and reopen if a
  subtask reopens); stages complete only when all required items are done
- Weighted progress calculation with manual and calculated modes; switching is
  audited and manual entry is rejected while calculated
- Interactive workflow editor and a Gantt timeline with dependency curves and
  a today marker on the task detail page

### Collaboration and notifications

- Task-scoped comment threads, optionally bound to a work item, with soft
  delete by the author or task managers
- Private attachments with checksums, size and extension limits,
  authorization-checked downloads, and storage paths never exposed
- In-app notification center with unread badge, polling, and click-through;
  recipients and their access are re-checked at delivery time, so revoked
  access never receives disclosure
- Transactional outbox: business mutations enqueue delivery events in the same
  database transaction; a background worker delivers with idempotent replay,
  exponential backoff, and recorded permanent failures
- Optional SMTP email channel (disabled by default) honoring per-user
  preferences; confidential tasks send the task number only, never the title

### Dashboards, reports, and exports

- Personal dashboard: assigned, accountable, overdue, and blocked stat cards,
  upcoming deadlines, blocked work, and recent activity
- Management overview with visible totals, completion rate, and weekly
  completions; My Tasks page with assigned, accountable, and all-visible tabs
- Department workspaces with workload cards, upcoming deadlines, blocked and
  overdue panels, and team assignments
- Reports: created-versus-completed trend, cycle time, status breakdown,
  milestone progress, blocker analysis, and department workload
- Dependency-free SVG charts on the dashboard: weekly trend, tasks-by-status
  donut, and workload by department
- Authorized CSV exports with formula-injection sanitization and audit events;
  every exported row re-passes the same access checks as the on-screen register
- PDF exports for the register, completion trend, and workload, rendered
  server-side with WeasyPrint using the organization's saved design

### CSV import center

- Staged pipeline: upload and validate (type, size, encoding, header
  structure), automatic column mapping with operator overrides, normalized
  preview, directory resolution, duplicate detection, row-level validation
  report, batched commit, and reconciliation summary download
- Legacy statuses and priorities map through approved mapping tables;
  unmapped values fail the row rather than being silently defaulted
- People resolve by exact email, exact employee code, then unique full-name
  match; ambiguous rows fail for manual resolution
- Retry-safe commits: already-imported identifiers are recognized and skipped,
  a committed job is immutable, and historical timestamps and percentages are
  preserved with provenance recorded
- Imports cannot grant access: new tasks receive the operator-approved initial
  visibility policy and no access grants

### Settings and theming

- Dark, light, and system themes with a no-flash pre-paint script and full
  dark tokens across every screen
- Appearance settings: six accent palettes and four interface font stacks,
  saved per user on the server and per device locally
- Organization settings: name and tagline shown in the PDF header and footer
- Roles and permissions editor with a grouped, searchable matrix; system roles
  stay read-only; all changes audited
- Users and access: grant login with a generated initial password, assign or
  revoke roles, reactivate or revoke accounts
- PDF design settings: paper size, orientation, accent color, document font,
  body size, cover page, header logo and organization name, footer text, page
  numbers, and table style, with a live sketch and a sample preview before
  saving

## Repository layout

```
├── nuxt.config.ts            # Nuxt config incl. /api proxy to :8000
├── app/                      # Nuxt app (pages, components, composables, middleware)
│   ├── pages/                # login, dashboard, tasks, my-tasks, departments,
│   │                         #   imports, reports, settings, admin areas
│   ├── components/           # sidebar navigation, notifications, comments,
│   │                         #   attachments, workflow panel, Gantt, charts,
│   │                         #   settings panels, confirm dialogs
│   ├── composables/          # API client, auth, notifications, appearance
│   ├── utils/display.ts      # shared status/priority tones and formatting
│   └── types/api.ts          # shared API types
├── backend/
│   ├── app/
│   │   ├── core/             # settings, security, logging, error envelope
│   │   ├── db/               # engine/session, base, portable UTC/JSON types
│   │   ├── models/           # users, sessions, RBAC, departments, audit,
│   │   │                     #   tasks, assignments, grants, activities,
│   │   │                     #   comments, attachments, notifications,
│   │   │                     #   preferences, outbox events, workflow
│   │   ├── domain/           # task lifecycle, access policy, assignment
│   │   │                     #   policy, workflow and progress rules,
│   │   │                     #   notification rules, CSV import rules
│   │   ├── api/v1/           # routers: auth, users, departments, roles,
│   │   │                     #   tasks, workflow, collaboration,
│   │   │                     #   notifications, dashboards, reports,
│   │   │                     #   imports, settings, health
│   │   ├── services/         # auth, audit, user admin, department, task,
│   │   │                     #   workflow, collaboration, notifications
│   │   │                     #   (outbox producer, worker, email), import,
│   │   │                     #   dashboard, report, PDF export
│   │   └── seeds/            # idempotent RBAC matrix, admin, demo data
│   ├── alembic/              # database migrations
│   └── tests/                # pytest suite (362 tests)
├── docs/                     # user guide, admin guide, support procedures,
│                             #   runbook, phase reports, launch assets
├── scripts/                  # dev and launch utilities
└── spec_full.json            # approved requirements document
```

## Running locally

Backend (from `backend/`):

```bash
uv sync                                   # install deps into .venv
uv run alembic upgrade head               # apply migrations
uv run python -m app.seeds.seed           # seed roles, admin, demo data (idempotent)
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

The seed also creates three departments, six demo staff accounts (password
`Interdec!2026`), and an 18-task register so dashboards, charts, and PDF
exports show meaningful data on first launch. Every step is idempotent.

## Environment configuration

Backend settings are env-driven with the `DECOPS_` prefix (see
`backend/app/core/config.py`). Switching to PostgreSQL in any real environment:

```
DECOPS_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/decops
DECOPS_SECURE_COOKIES=true
DECOPS_ENVIRONMENT=production
DECOPS_SESSION_SECRET_KEY=<generated secret>
```

## Security controls

- Argon2id password hashing; opaque session tokens stored only as SHA-256 hashes
- HttpOnly + SameSite=Lax cookies; `secure` flag configurable for HTTPS deployments
- Login throttling with temporary lockout; account deactivation enforcement
- Non-enumerating authentication errors (unknown user and wrong password are
  indistinguishable)
- 404 (not 403) for protected resources to avoid confirming existence
- Append-only audit events for login/logout/failures; sensitive keys redacted
- Structured JSON logs with request ids; consistent error envelope
- Security headers middleware: `nosniff`, frame `DENY`, `no-referrer`,
  restrictive CSP, `no-store`, conditional HSTS
- Optimistic-concurrency `version` columns on tasks and workflow items

## Test suite

```bash
cd backend && uv run pytest   # 362 tests
```

Coverage spans authentication, authorization, task access policy, assignment
policy, cross-task isolation, lifecycle transitions, audit coverage, workflow
domain and API rules, comments and attachments privacy, notifications and
outbox retry safety, dashboards and reports reconciliation and leak
prevention, authorized exports, the CSV import pipeline, launch assets, and
security hardening probes.

## Production launch

- `scripts/start_prod.sh`: migrations, seed, launch drill, frontend build,
  then API and Nuxt servers with an enforced production posture
- `scripts/launch_phase10.py`: idempotent, audited launch drill covering
  configuration and database preflight, account provisioning from
  `docs/launch/accounts_manifest.csv`, a validated register import through
  the real import pipeline, and a per-role HTTP smoke matrix
- `scripts/monitor_phase10.py`: health, adoption, register health, outbox
  backlog, and failed-login burst alerting with JSON snapshots
- Operations documentation: `docs/runbook.md` (deployment, backups, incident
  response), `docs/user-guide.md`, `docs/admin-guide.md`,
  `docs/support-procedures.md`, and `docs/reports/` (security, performance,
  restore, UAT sign-off, and launch reports)
