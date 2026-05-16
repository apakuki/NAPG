#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

for name in frontend agent; do
  pidfile=".${name}.pid"
  if [ -f "$pidfile" ]; then
    pid=$(cat "$pidfile")
    if kill -0 "$pid" 2>/dev/null; then
      echo "stopping $name (pid $pid)"
      kill "$pid"
    else
      echo "$name pidfile present but process not running"
    fi
    rm -f "$pidfile"
  else
    echo "no pidfile for $name"
  fi
done
