#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

echo "Starting GroundedNews..."

# Backend
echo "  → Backend on http://localhost:8000"
cd backend
"$SCRIPT_DIR/venv/bin/uvicorn" main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
cd "$SCRIPT_DIR"

# Frontend
echo "  → Frontend on http://localhost:3000"
cd frontend
npm run dev &
FRONTEND_PID=$!
cd "$SCRIPT_DIR"

echo ""
echo "GroundedNews running:"
echo "  Web UI:  http://localhost:3000"
echo "  API:     http://localhost:8000"
echo "  API docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" SIGINT SIGTERM
wait
