#!/usr/bin/env bash
# Start the frontend dev server (Linux/macOS). Clears an orphan process and .next first.
set -euo pipefail
PORT="${1:-3000}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if command -v lsof >/dev/null 2>&1; then
  pids="$(lsof -ti tcp:"$PORT" -sTCP:LISTEN || true)"
  if [ -n "$pids" ]; then echo "Stopping orphan process(es) $pids on port $PORT"; kill -9 $pids; fi
fi

cd "$ROOT/frontend"
rm -rf .next
exec npm run dev -- --port "$PORT"
