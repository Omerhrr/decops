# DecOps — Operations Management System (Interdec)

Internal task and workflow management system. This repository currently contains the
**Phase 2 (Application Foundation)**, **Phase 3 (Identity & Authorization)**,
**Phase 4 (Task Management)**, and **Phase 5 (Workflow Engine)** releases from the
approved implementation plan — running frontend + backend, database migrations,
secure authentication, RBAC, user/department administration, a task access policy
engine, full task management (register, detail, lifecycle transitions, assignments,
access grants, activity history), the workflow engine (stages, milestones, subtasks,
dependencies, progress calculation, Gantt timeline, workflow editor), audit logging,
structured error handling, and an automated test suite (202 tests).

## Stack (pinned per spec)

| Layer     | Technology                                                        |
|-----------|-------------------------------------------------------------------|
| Frontend  | Nuxt 4 (Vue 3, TypeScript, Tailwind CSS 4) — port **3000**        |
| Backend   | FastAPI (Python 3.12, Pydantic v2, SQLAlchemy 2.1) — port **8000**|
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
│   ├── composables/        # useApi (typed client, SSR cookie forwarding), useAuth
│   └── middleware/         # Global auth guard
├── backend/
│   ├── app/
│   │   ├── core/           # Settings, security, logging, error envelope
│   │   ├── db/             # Engine/session, base, portable types (UTCDateTime, JSON)
│   │   ├── models/         # users, sessions, RBAC, departments, audit_events,
│   │   │                   #   tasks, task_assignments, task_departments,
│   │   │                   #   task_access_grants, task_activities (Phase 4)
│   │   ├── domain/         # Task lifecycle state machine, access policy engine
│   │   │                   #   (grant levels), assignment authorization (pure logic)
│   │   ├── api/v1/         # /api/v1 routers: auth, users, departments, roles, tasks,
│   │   │                   #   health
│   │   ├── services/       # auth, audit, user admin, department, task services
│   │   └── seeds/          # Idempotent RBAC matrix + admin seed
│   ├── alembic/            # Migrations (foundation + Phase 4 task tables)
│   └── tests/              # Pytest: auth, authorization, transitions, audit,
│   │                       #   access policy, assignment policy, cross-task isolation,
│   │                       #   task CRUD/transitions/assignments/grants (143 tests)
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

## API surface (Phase 2 + Phase 3)

- `POST /api/v1/auth/login` — session login (Argon2id, throttling, audited)
- `POST /api/v1/auth/logout` — session revocation (immediate)
- `GET  /api/v1/auth/me` — profile, global roles, permission codes
- `GET  /api/v1/users` — admin-only, paginated directory (filter by q/status)
- `POST /api/v1/users` — create employee (audited)
- `GET/PATCH /api/v1/users/{id}` — profile detail / update (audited)
- `POST /api/v1/users/{id}/status` — activate/deactivate (revokes sessions, audited)
- `POST /api/v1/users/{id}/roles` — assign global role (`roles.assign`, audited)
- `DELETE /api/v1/users/{id}/roles/{role_id}` — revoke role (audited)
- `GET  /api/v1/departments` — list with member counts
- `POST /api/v1/departments` — create (optional lead → lead membership, audited)
- `GET/PATCH /api/v1/departments/{id}` — detail incl. memberships / update (audited)
- `POST /api/v1/departments/{id}/members` — assign employee (audited)
- `DELETE /api/v1/departments/{id}/members/{user_id}` — remove employee (audited)
- `GET  /api/v1/roles`, `GET /api/v1/roles/permissions` — RBAC catalogue
- `GET  /api/v1/tasks` — authorization-filtered register (status/priority/q/department)
- `POST /api/v1/tasks` — create with valid access policy (tasks.create, audited)
- `GET  /api/v1/tasks/{id}` — detail (engine VIEW; 404 on denial)
- `PATCH /api/v1/tasks/{id}` — permitted fields, optimistic concurrency (AC-18)
- `POST /api/v1/tasks/{id}/transition` — validated lifecycle transitions with
  reason/explanation enforcement and per-target operation authorization
- `GET  /api/v1/tasks/{id}/transition-options` — allowed next statuses for the UI
- `POST/DELETE /api/v1/tasks/{id}/assignments[/{assignment_id}]` — accountable/supporting
  PM assignment (DEC-02, assigning user recorded, audited)
- `POST /api/v1/tasks/{id}/departments` — link participating department
- `POST/DELETE /api/v1/tasks/{id}/access-grants[/{grant_id}]` — view/operate/manage/denied
  grants; immediate revocation; audited (engine CHANGE_VISIBILITY)
- `GET  /api/v1/tasks/{id}/activity` — task activity timeline (AC-12)
- `GET  /api/v1/health` — liveness + database check
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
cd backend && uv run pytest   # 202 tests: transitions, auth, authorization, audit,
                              #   access policy, assignment policy, cross-task isolation,
                              #   task CRUD/edits/transitions/assignments/grants/activity,
                              #   workflow state machines, dependency cycles, sequential/
                              #   parallel gating, completion rules, progress calculation,
                              #   workflow API authz + optimistic concurrency
```

## Task access policy engine (Phase 3 + Phase 4 deliverable)

`backend/app/domain/access_policy.py` implements the spec's four visibility modes
(`private`, `participants`, `department_scoped`, `custom`) as pure, stateless logic:

- Every task carries an explicit, self-contained policy (mode + grants + denials)
- Precedence: explicit denial > permitted admin > explicit grant > creator > scope
- **Grant levels (Phase 4)**: `view` (read/comment), `operate` (default — update,
  coordinate), `manage` (administer); visibility changes always additionally
  require `tasks.update_assigned`
- Grants are embedded per policy, so access to one task can never leak to another
  (proven by `tests/test_isolation.py` and API-level tests — the Phase 3 exit criterion)
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
  predecessors satisfy the edge — an audited scope decision)
- **Completion rules**: a milestone with required subtasks cannot be completed
  by hand — it auto-completes when the last required subtask completes (and
  reopens if a subtask reopens); a stage can complete only when all required,
  non-cancelled items are done
- **Progress calculation (AC-06)**: weighted stages × required items; optional
  and cancelled items excluded; subtasks roll up into their milestone (no double
  counting); manual vs calculated modes are explicit — switching is audited and
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

## Decisions defaulted (from spec §decisions_to_confirm_with_interdec)

- DEC-02: one accountable PM, multiple supporting PMs (modelled in schema)
- DEC-11: timestamps stored in UTC (`UTCDateTime`), rendered client-side
- DEC-12: local credential management for now; `authentication_reference`
  column is SSO-ready
- DEC-13: in-app foundation only; notification tables arrive in Phase 6
- These remain subject to Interdec sign-off per the spec.

## Roadmap

Phases 6–10 (collaboration & notifications, dashboards & reporting, CSV
migration, hardening, launch) follow the approved `implementation_phases`
in `spec_full.json`.
