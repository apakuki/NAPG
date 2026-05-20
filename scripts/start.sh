#!/usr/bin/env bash
set -euo pipefail

# Start the NAPG agent API and the Next.js frontend in dev mode.
# The agent runs uvicorn on 127.0.0.1:8000 serving napg.api; the frontend
# proxies /api/status to it. Stop both with scripts/stop.sh.

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if [ ! -f .env ]; then
  echo "missing .env — copy .env.example and fill in keys" >&2
  exit 1
fi

echo "starting frontend (npm run dev) in background"
(cd frontend && npm run dev) &
FRONTEND_PID=$!
echo $FRONTEND_PID > .frontend.pid

echo "starting agent API (uv run python -m napg serve) in background"
(cd agent && uv run python -m napg serve) &
AGENT_PID=$!
echo $AGENT_PID > .agent.pid

echo "frontend pid=$FRONTEND_PID, agent pid=$AGENT_PID"
echo "dashboard: http://localhost:3000"
echo "agent api: http://127.0.0.1:8000/api/status"
echo "stop with scripts/stop.sh"
