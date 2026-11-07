#!/bin/sh
# Migrate, seed (idempotent: roles + admin; demo data only outside production),
# then serve. A single worker on purpose: the outbox worker runs in-process.
set -eu
mkdir -p "${DECOPS_ATTACHMENT_STORAGE_DIR:-/data/attachments}" "${DECOPS_IMPORT_STORAGE_DIR:-/data/imports}"
echo "[decops] running migrations"
alembic upgrade head
echo "[decops] seeding"
python -m app.seeds.seed
echo "[decops] starting API on :${PORT:-8000}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-*}" --no-server-header
