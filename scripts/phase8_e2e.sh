#!/bin/bash
# Phase 8 E2E in a single session: backend stays alive for the duration.
set -x
cd /home/z/my-project/backend
setsid nohup uv run uvicorn app.main:app --port 8000 >> /home/z/my-project/scripts/uvicorn.log 2>&1 < /dev/null &
sleep 7

# 1) Revalidate the demo job with the intra-file duplicate fix
curl -s -c /tmp/cookies.txt -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@interdec.com","password":"DecOps!2026"}' -o /dev/null
JOB=d8708d64-66e9-4992-9fc0-3d52eeb5672d
curl -s -b /tmp/cookies.txt -X PATCH http://localhost:8000/api/v1/imports/$JOB \
  -H "Content-Type: application/json" -d '{}' -o /tmp/patch_result.json -w "patch:%{http_code}\n"
cat /tmp/patch_result.json | python3 -m json.tool | head -12
curl -s -b /tmp/cookies.txt http://localhost:8000/api/v1/imports/$JOB/report | python3 -c "
import json,sys
r = json.load(sys.stdin)
for row in r['rows']:
    dup = [d['kind'] for d in row['duplicates']]
    print(row['row_number'], row['source_task_id'], row['status'], 'dup:', dup, 'review:', (row['normalized'] or {}).get('duplicate_review'))
"

# 2) Browser: reload, reselect job, screenshot the report
agent-browser reload >/dev/null
agent-browser wait --load networkidle >/dev/null
agent-browser find text "phase8_demo_import.csv" click >/dev/null
sleep 2
agent-browser screenshot /home/z/my-project/scripts/phase8_import_report.png >/dev/null
agent-browser snapshot -i 2>&1 | rg -i "Commit \d+ rows" | head -2

# 3) Commit through the UI (dialog confirm)
agent-browser find role button click --name "Commit 3 rows" >/dev/null 2>&1 || agent-browser snapshot -i 2>&1 | rg "Commit"
sleep 1
agent-browser dialog accept >/dev/null 2>&1
sleep 3
agent-browser wait --load networkidle >/dev/null
agent-browser screenshot /home/z/my-project/scripts/phase8_import_committed.png >/dev/null
agent-browser snapshot -i 2>&1 | rg -i "committed|already" | head -8
echo "=== BROWSER E2E DONE ==="
