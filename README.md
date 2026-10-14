# DecOps — Operations Management System (Interdec)

Internal task and workflow management system. This repository currently contains the
**Phase 2: Application Foundation** release from the approved implementation plan —
running frontend + backend, database migrations, secure authentication, RBAC seed data,
audit logging, structured error handling, and an automated test suite.

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
│   ├── composables/        # useApi (typed client), useAuth (session state)
│   └── middleware/         # Global auth guard
├── backend/
│   ├── app/
│   │   ├── core/           # Settings, security, logging, error envelope
│   │   ├── db/             # Engine/session, base, portable types (UTCDateTime, JSON)
│   │   ├── models/         # users, sessions, RBAC, departments, audit_events
│   │   ├── domain/         # Task lifecycle state machine (pure logic)
│   │   ├── api/v1/         # /api/v1 routers: auth, users, health
│   │   ├── services/       # auth_service, audit_service
│   │   └── seeds/          # Idempotent RBAC matrix + admin seed
│   ├── alembic/            # Migrations
│   └── tests/              # Pytest: auth, authorization, transitions, audit
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

## API surface (Phase 2)

- `POST /api/v1/auth/login` — session login (Argon2id, throttling, audited)
- `POST /api/v1/auth/logout` — session revocation (immediate)
- `GET  /api/v1/auth/me` — profile, global roles, permission codes
- `GET  /api/v1/users` — admin-only, paginated directory (user management lands in Phase 3)
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
cd backend && uv run pytest   # 46 tests: transitions, auth, authorization, audit
```

## Decisions defaulted (from spec §decisions_to_confirm_with_interdec)

- DEC-02: one accountable PM, multiple supporting PMs (modelled in schema)
- DEC-11: timestamps stored in UTC (`UTCDateTime`), rendered client-side
- DEC-12: local credential management for now; `authentication_reference`
  column is SSO-ready
- DEC-13: in-app foundation only; notification tables arrive in Phase 6
- These remain subject to Interdec sign-off per the spec.

## Roadmap

Phases 3–10 (identity & authorization deepening, task management, workflow engine,
collaboration, dashboards, CSV migration, hardening, launch) follow the approved
`implementation_phases` in `spec_full.json`.
