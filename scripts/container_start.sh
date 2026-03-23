#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python}"

echo "Applying database migrations..."
"$PYTHON_BIN" -m alembic upgrade head

echo "Starting single-process app runtime..."
exec ./scripts/run_single_process.sh
