#!/bin/bash
# Phase 9 UAT walkthrough (single session so the backend stays alive).
cd /home/z/my-project/backend
pkill -f "uvicorn app.main:app" 2>/dev/null || true
sleep 1
setsid nohup uv run uvicorn app.main:app --port 8000 >> /home/z/my-project/scripts/uvicorn.log 2>&1 < /dev/null &
sleep 8
curl -s -o /dev/null -w "backend up: %{http_code}\n" http://localhost:8000/api/v1/health

B="agent-browser"
S=/home/z/my-project/scripts

# goto_login + login_as <email> <password>
goto_login() {
 $B open http://localhost:3000/login >/dev/null
 $B wait --load networkidle >/dev/null
 sleep 1
}

logout() {
 $B find text "Sign out" click >/dev/null 2>&1
 sleep 2
 $B wait --load networkidle >/dev/null
}

login_as() {
 local email="$1" password="$2"
 local snap refs er pr br
 snap=$($B snapshot -i 2>&1)
 er=$(printf '%s' "$snap" | rg -o 'textbox "Work email" \[required, ref=([e0-9]+)\]' -r '$1')
 pr=$(printf '%s' "$snap" | rg -o 'textbox "Password" \[required, ref=([e0-9]+)\]' -r '$1')
 br=$(printf '%s' "$snap" | rg -o 'button "Sign in" \[disabled?, ref=([e0-9]+)\]' -r '$1')
 $B fill "@$er" "$email" >/dev/null
 $B fill "@$pr" "$password" >/dev/null
 $B click "@$br" >/dev/null
 sleep 3
 $B wait --load networkidle >/dev/null
 echo " logged in as $email (url: $($B get url))"
}

echo "=== JOURNEY 1: Management - dashboard + reports"
goto_login
login_as "manager@interdec.com" "Secret!1234"
$B screenshot $S/uat_1_manager_dashboard.png >/dev/null
$B find text "Reports" click >/dev/null
sleep 2
$B wait --load networkidle >/dev/null
$B screenshot $S/uat_2_manager_reports.png >/dev/null
echo " reports page reachable"

echo "=== JOURNEY 2: Lead - departments workload"
logout
goto_login
login_as "ops.lead@interdec.com" "Secret!1234"
$B find text "Departments" click >/dev/null
sleep 2
$B wait --load networkidle >/dev/null
$B screenshot $S/uat_3_lead_departments.png >/dev/null
echo " departments page reachable for lead"

echo "=== JOURNEY 3: Auditor - reports/exports"
logout
goto_login
login_as "auditor@interdec.com" "Secret!1234"
$B find text "Reports" click >/dev/null 2>&1 || echo " (no Reports nav for auditor)"
sleep 2
$B wait --load networkidle >/dev/null
$B screenshot $S/uat_4_auditor_reports.png >/dev/null
echo " auditor journey done"

echo "=== JOURNEY 4: Admin - imports center"
logout
goto_login
login_as "admin@interdec.com" "DecOps!2026"
$B find text "Imports" click >/dev/null
sleep 2
$B wait --load networkidle >/dev/null
$B screenshot $S/uat_5_admin_imports.png >/dev/null
$B snapshot 2>&1 | rg -i "import history" | head -1

echo "=== UAT WALKTHROUGH COMPLETE ==="
