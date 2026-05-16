#!/usr/bin/env bash
set -euo pipefail

# Start the NAPG agent and the Next.js frontend in dev mode.
# Replace with real entry points once Phase 1 lands.

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

echo "starting agent (uv run python -m napg) in background"
(cd agent && uv run python -m napg) &
AGENT_PID=$!
echo $AGENT_PID > .agent.pid

echo "frontend pid=$FRONTEND_PID, agent pid=$AGENT_PID"
echo "stop with scripts/stop.sh"
