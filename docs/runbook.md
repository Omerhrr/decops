# DecOps Production Runbook

Operational procedures for running DecOps in production (Interdec internal
deployment). Companion documents: `docs/reports/phase9_*` (test reports),
`README.md` (architecture), `spec_full.json` (requirements).

## 1. Components

| Component | Technology | Notes |
|---|---|---|
| Frontend | Nuxt 4 (Node 20+) | SSR + `/api/**` proxy to the backend |
| Backend | FastAPI (Python 3.12), Uvicorn workers | Modular monolith |
| Database | PostgreSQL 15+ (production), SQLite (dev only) | SQLAlchemy 2.1 + Alembic |
| Object storage | Local directories (`backend/var/attachments`, `backend/var/imports`) | Swap to S3-compatible storage via the storage-key abstraction when required |

## 2. First deployment

1. **Provision PostgreSQL**: create database `decops` and a dedicated role;
   network-isolate it (private subnet / VPC security group); enable TLS.
2. **Configure the backend** via environment variables (12-factor, `DECOPS_`
   prefix) — never commit secrets:
   ```bash
   DECOPS_DATABASE_URL=postgresql+psycopg://decops:<password>@<host>:5432/decops
   DECOPS_ENVIRONMENT=production
   DECOPS_DEBUG=false
   DECOPS_SECURE_COOKIES=true            # enables `Secure` cookie flag + HSTS
   DECOPS_SESSION_SECRET_KEY=<openssl rand -hex 32>
   DECOPS_SEED_ADMIN_EMAIL=<approved admin>
   DECOPS_SEED_ADMIN_PASSWORD=<initial secret, rotated at first login>
   DECOPS_EMAIL_NOTIFICATIONS_ENABLED=true   # once SMTP is approved
   DECOPS_SMTP_HOST=... DECOPS_SMTP_PORT=587 DECOPS_SMTP_USERNAME=...
   ```
3. **Run migrations + seed** (idempotent):
   ```bash
   cd backend && uv run alembic upgrade head && uv run python -m app.seeds.seed
   ```
4. **Serve the API** behind a process manager:
   ```bash
   uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
   ```
   (systemd unit recommended; the transactional-outbox worker runs inside the
   app lifespan — exactly ONE worker must own it in multi-worker setups, or
   scale it out per the note in §6.)
5. **Serve the frontend**: `npm run build && node .output/server/index.mjs`
   with `NUXT_PUBLIC_API_BASE`/proxy target pointing at the API origin.
6. **Reverse proxy** (nginx/Caddy): TLS termination (A-grade config), forward
   `X-Request-Id`, gzip/brotli, `client_max_body_size 25m` for attachment
   uploads, and no caching of `/api/*` (the API already sends `Cache-Control:
   no-store`).

## 3. Deploying a new release

```bash
# zero-downtime, backwards-compatible migrations only
git fetch && git checkout <tag>
cd backend && uv sync && uv run alembic upgrade head   # 1) schema
# 2) rolling-restart API workers, then 3) build+restart frontend
node -e "1" && npm run build
```

Rollback: redeploy the previous tag; migrations are additive — a rollback
never requires downgrading the schema within a release window (verify against
`alembic history` before destructive changes).

## 4. Backup & restore

**Backup (nightly):**
```bash
pg_dump --format=custom --file /backups/decops-$(date +%F).dump "$DECOPS_DATABASE_URL"
rsync -a backend/var/ /backups/var-$(date +%F)/   # attachments + import artifacts
```
Keep 30 daily + 12 monthly backups, encrypted at rest (restic/borg recommended).

**Restore (tested in Phase 9 — `docs/reports/phase9_restore_report.md`):**
```bash
createdb decops_restored
pg_restore --clean --if-exists --dbname decops_restored /backups/decops-YYYY-MM-DD.dump
psql -d decops_restored -c "SELECT version_num FROM alembic_version;"   # must match release head
psql -d decops_restored -c "PRAGMA" # n/a; use: ANALYZE; and run app smoke checks
rsync -a /backups/var-YYYY-MM-DD/ backend/var/
```
Verification checklist (mirrors the Phase 9 drill): row counts reconcile with
the backup manifest, damaged data absent, migration head matches the release,
no FK violations (`django`-free check: `psql -c "ANALYZE;"` + app smoke tests),
attachment/`storage_key` files present. Restore into a staging URL first; cut
over only after checks pass.

**Monthly drill**: repeat the restore into staging and time it (RTO target:
< 1 h; RPO: ≤ 24 h with nightly backups).

## 5. Monitoring & health

- **Liveness**: `GET /api/v1/health` → `{"status": "ok", ...}` (checks DB);
  wire to the load balancer + uptime monitor (5 s interval, alert on 3
  failures).
- **Logs**: structured JSON with `request_id` correlation (`x-request-id`
  response header). Ship to the log aggregator; alert on
  `level=ERROR` rate and `request_failed` events.
- **Audit**: `audit_events` is the security-relevant trail (append-only);
  alert on unexpected bursts of `auth.login_failed` (credential stuffing) or
  `import.committed` outside business hours.
- **Outbox**: monitor `outbox_events` stuck in `pending`/`processing`
  beyond `outbox_max_attempts` → `permanent_failure` rows require attention.
- **Metrics to add at launch** (exposed via middleware or exporter): request
  duration histogram per route, DB pool saturation, worker queue depth.

## 6. Known operational constraints

- The outbox worker runs inside the API process (lifespan). With multiple
  Uvicorn workers, deliveries are idempotent (unique
  `(outbox_event_id, recipient_id)` + claimed status transitions), but set
  `DECOPS_OUTBOX_WORKER_ENABLED=false` on all but one worker (or one dedicated
  worker process) to avoid duplicate work.
- SQLite is **not** supported in production (single-writer, no network).
  The dev default exists only for the sandbox.
- Attachment/CSV storage is local-disk based; backups MUST include
  `backend/var/` or downloads break after restore (§4).

## 7. Pre-launch checklist

- [ ] PostgreSQL provisioned, TLS on, credentials in the secret manager
- [ ] `DECOPS_*` production environment configured (no defaults)
- [ ] `alembic upgrade head` + idempotent seed executed
- [ ] Approved initial admin account created; password rotated at first login
- [ ] Approved user accounts created (Phase 10 objective)
- [ ] Validated task register imported via the import center (Phase 10)
- [ ] TLS + reverse proxy in place (`Secure` cookies → HSTS active)
- [ ] Nightly backups + monthly restore drill scheduled (§4)
- [ ] Uptime monitor on `/api/v1/health`; log shipping live (§5)
- [ ] Infrastructure-level penetration test scheduled (outside app scope)
- [ ] Interdec sign-off recorded (`docs/reports/phase9_uat_signoff.md`)

## 8. Incident procedures (summary)

1. **Triage**: check `/api/v1/health`, recent structured logs (`request_id`
   correlation), and `audit_events` for the blast radius.
2. **Suspected data issue**: freeze writes (read-only mode via proxy) and run
   the §4 restore procedure into staging; compare with the live DB before
   deciding on a cutover.
3. **Suspected security event**: revoke sessions at the DB level
   (`user_sessions` delete/flag), rotate `DECOPS_SESSION_SECRET_KEY` (invalidates
   all opaque tokens) and force password resets via user administration;
   preserve `audit_events` (append-only) for forensics.
4. **Import mishap**: imports are staged before commit; a committed import is
   audited with per-row task IDs (`import_jobs.committed_task_ids`) enabling
   surgical rollback of imported tasks by ID.
5. **Post-incident**: record a timeline from logs + audit events; file defects
   with the `request_id` evidence chain.
