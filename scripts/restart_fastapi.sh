#!/usr/bin/env bash
set -euo pipefail

# Restarts the FastAPI server (uvicorn) for this repo.
# - If something is already listening on PORT, it will be stopped first.
# - Then uvicorn is started in the foreground.
#
# Usage:
#   ./scripts/restart_fastapi.sh
#
# Optional env vars:
#   PORT=8000 HOST=127.0.0.1 APP=app.main:app RELOAD=1 FORCE_KILL=0

PORT="${PORT:-8000}"
HOST="${HOST:-127.0.0.1}"
APP="${APP:-app.main:app}"
RELOAD="${RELOAD:-1}"
FORCE_KILL="${FORCE_KILL:-0}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

args=(--host "$HOST" --port "$PORT")
if [[ "$RELOAD" == "1" ]]; then
  args+=(--reload)
fi

find_listeners() {
  # macOS/Linux: list PIDs listening on TCP port
  lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null || true
}

stop_pid() {
  local pid="$1"

  if ! kill -0 "$pid" 2>/dev/null; then
    return 0
  fi

  local cmd=""
  cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"

  if [[ "$cmd" == *uvicorn* ]] && [[ "$cmd" == *"$APP"* ]]; then
    echo "Stopping uvicorn (pid=$pid): $cmd"
    kill "$pid" 2>/dev/null || true
  else
    echo "Port $PORT is in use by pid=$pid:"
    echo "  $cmd"
    if [[ "$FORCE_KILL" == "1" ]]; then
      echo "FORCE_KILL=1 set; stopping pid=$pid"
      kill "$pid" 2>/dev/null || true
    else
      echo "Refusing to stop it. Set FORCE_KILL=1 to force."
      return 1
    fi
  fi

  # Wait up to ~5s for clean shutdown, then SIGKILL.
  for _ in {1..50}; do
    if ! kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
    sleep 0.1
  done

  echo "Process pid=$pid did not exit; sending SIGKILL"
  kill -9 "$pid" 2>/dev/null || true
}

pids="$(find_listeners)"
if [[ -n "${pids// }" ]]; then
  for pid in $pids; do
    stop_pid "$pid"
  done
fi

echo "Starting: $APP on http://$HOST:$PORT"
if command -v uv >/dev/null 2>&1; then
  exec uv run uvicorn "$APP" "${args[@]}"
elif [[ -x ".venv/bin/uvicorn" ]]; then
  exec ".venv/bin/uvicorn" "$APP" "${args[@]}"
else
  exec uvicorn "$APP" "${args[@]}"
fi
