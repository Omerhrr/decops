#!/usr/bin/env bash
# DecOps production launcher (runbook §2 steps 3-5, sandbox-validated).
# Usage: ./scripts/start_prod.sh
set -euo pipefail
cd "$(dirname "$0")/.."

# --- Production posture (override via environment in real deployments) ---
export DECOPS_ENVIRONMENT="${DECOPS_ENVIRONMENT:-production}"
export DECOPS_DEBUG="${DECOPS_DEBUG:-false}"
export DECOPS_SECURE_COOKIES="${DECOPS_SECURE_COOKIES:-true}"
export DECOPS_SESSION_SECRET_KEY="${DECOPS_SESSION_SECRET_KEY:?DECOPS_SESSION_SECRET_KEY must be set (openssl rand -hex 32)}"
# DECOPS_DATABASE_URL must point at PostgreSQL in production (SQLite is dev-only).
: "${DECOPS_DATABASE_URL:?DECOPS_DATABASE_URL must be set (postgresql+psycopg://...)}"

echo "[1/5] Migrations + idempotent seed"
(cd backend && uv run alembic upgrade head && uv run python -m app.seeds.seed)

echo "[2/5] Approved accounts + validated register (launch drill, idempotent)"
(cd backend && uv run python ../scripts/launch_phase10.py --skip-smoke) || {
 echo "launch preflight/provisioning failed - aborting"; exit 1; }

echo "[3/5] Building frontend"
bun run build

echo "[4/5] Starting API (port 8000)"
(cd backend && nohup uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 \
 --proxy-headers --forwarded-allow-ips='*' > ../.uvicorn-prod.log 2>&1 &)

echo "[5/5] Starting Nuxt server (port 3000)"
PORT=3000 nohup node .output/server/index.mjs > .nuxt-prod.log 2>&1 &

sleep 3
curl -fsS http://localhost:8000/api/v1/health
echo
echo "DecOps production stack is up. Monitor: python3 scripts/monitor_phase10.py"
