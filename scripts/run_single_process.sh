#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-./.venv/bin/python}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

exec "$PYTHON_BIN" -m uvicorn app.main:app --host "$HOST" --port "$PORT" --workers 1 "$@"
