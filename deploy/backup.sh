#!/bin/sh
# Runs inside the `backup` container: one backup at BACKUP_HOUR_UTC every day.
# Also runs once at start so a fresh install has a restore point immediately.
set -eu
KEEP="${BACKUP_KEEP_DAYS:-14}"
HOUR="${BACKUP_HOUR_UTC:-2}"

run_backup() {
  ts="$(date -u +%Y%m%dT%H%M%SZ)"
  echo "[backup] $ts starting"
  if pg_dump --no-owner --format=custom --file="/backups/db_$ts.dump.tmp"; then
    mv "/backups/db_$ts.dump.tmp" "/backups/db_$ts.dump"
  else
    rm -f "/backups/db_$ts.dump.tmp"; echo "[backup] DATABASE DUMP FAILED"; return 1
  fi
  tar -czf "/backups/files_$ts.tar.gz" -C /data . && echo "[backup] files archived"
  find /backups -type f \( -name 'db_*' -o -name 'files_*' \) -mtime +"$KEEP" -delete
  echo "[backup] done: $(ls /backups | wc -l) files kept"
}

sleep 20   # let the database finish starting
run_backup || true
while true; do
  now_h="$(date -u +%H | sed 's/^0//')"; now_h="${now_h:-0}"
  if [ "$now_h" -eq "$HOUR" ]; then run_backup || true; sleep 3700; else sleep 600; fi
done
