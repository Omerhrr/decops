#!/bin/bash
# (Re)start both DecOps dev servers detached from the current shell.
cd /home/z/my-project/backend || exit 1
pkill -f "uvicorn app.main:app" 2>/dev/null
pkill -f "nuxt dev" 2>/dev/null
sleep 1
setsid nohup uv run uvicorn app.main:app --port 8000 > /home/z/my-project/scripts/uvicorn.log 2>&1 < /dev/null &
cd /home/z/my-project || exit 1
setsid nohup npx nuxt dev > /tmp/nuxt-dev.log 2>&1 < /dev/null &
sleep 12
B=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/health)
F=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/login)
echo "backend:$B frontend:$F"
