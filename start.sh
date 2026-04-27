#!/bin/bash
set -e

# Start automation daemon in background
python scripts/run_automation.py &
WORKER_PID=$!

cleanup() {
    kill "$WORKER_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Start web server in foreground (Railway watches this process)
exec gunicorn -w 2 -b "0.0.0.0:${PORT:-8080}" web.app:app
