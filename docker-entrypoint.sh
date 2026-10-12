#!/bin/bash
set -euo pipefail

uvicorn main:app --app-dir /app/backend --host 127.0.0.1 --port 8000 &
backend_pid=$!
node /app/frontend/server.js &
frontend_pid=$!

cleanup() {
  kill "$backend_pid" "$frontend_pid" 2>/dev/null || true
  wait "$backend_pid" "$frontend_pid" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 0' SIGINT SIGTERM

# Stop the container if either service exits.
status=0
wait -n "$backend_pid" "$frontend_pid" || status=$?
exit "$status"
