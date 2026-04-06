#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
HOST="127.0.0.1"
PORT="8000"
URL="http://$HOST:$PORT"

cd "$ROOT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required but not installed."
    exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m app.seed

cleanup() {
    if [ -n "${SERVER_PID:-}" ] && kill -0 "$SERVER_PID" >/dev/null 2>&1; then
        kill "$SERVER_PID" >/dev/null 2>&1 || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi
}

trap cleanup EXIT INT TERM

python -m uvicorn app.main:app --host "$HOST" --port "$PORT" --reload &
SERVER_PID=$!

for _ in $(seq 1 30); do
    if python - <<'PY'
import urllib.request

try:
    with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=1) as response:
        raise SystemExit(0 if response.status == 200 else 1)
except Exception:
    raise SystemExit(1)
PY
    then
        break
    fi
    sleep 1
done

open_browser() {
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$URL" >/dev/null 2>&1 &
        return
    fi
    if command -v open >/dev/null 2>&1; then
        open "$URL" >/dev/null 2>&1 &
        return
    fi
    echo "Open this URL in your browser: $URL"
}

open_browser

echo "Project Time Tracker is running at $URL"
echo "Press Ctrl+C to stop."

wait "$SERVER_PID"
