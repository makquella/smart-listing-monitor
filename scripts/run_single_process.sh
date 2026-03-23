#!/usr/bin/env bash
set -euo pipefail

DEFAULT_PYTHON_BIN="./.venv/bin/python"
if [[ -x "$DEFAULT_PYTHON_BIN" ]]; then
  PYTHON_BIN="${PYTHON_BIN:-$DEFAULT_PYTHON_BIN}"
else
  PYTHON_BIN="${PYTHON_BIN:-python}"
fi
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

exec "$PYTHON_BIN" -m uvicorn \
  app.main:app \
  --host "$HOST" \
  --port "$PORT" \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips='*' \
  "$@"
