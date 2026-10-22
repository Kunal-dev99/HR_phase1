#!/usr/bin/env bash
# Start the FastAPI backend (Linux/macOS). Clears an orphan process on the port first.
set -euo pipefail
PORT="${1:-8000}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if command -v lsof >/dev/null 2>&1; then
  pids="$(lsof -ti tcp:"$PORT" -sTCP:LISTEN || true)"
  if [ -n "$pids" ]; then echo "Stopping orphan process(es) $pids on port $PORT"; kill -9 $pids; fi
fi

cd "$ROOT/backend"
# shellcheck disable=SC1091
source .venv/bin/activate
exec uvicorn app.main:app --reload --no-access-log --port "$PORT"
