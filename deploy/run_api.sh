#!/usr/bin/env bash
# Start the analysis API on one backend machine.
#
#   deploy/run_api.sh              # port 8000, one worker per CPU core
#   PORT=5288 WORKERS=4 deploy/run_api.sh
#
# Each worker is a separate process, so analyses on different workers run
# truly in parallel. MAX_CONCURRENT_ANALYSES (per worker) and the other
# limits in docs/API.md can be set in the environment as well.
set -euo pipefail

cd "$(dirname "$0")/.."
source venv/bin/activate

PORT="${PORT:-8000}"
WORKERS="${WORKERS:-$(nproc)}"

exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --workers "$WORKERS" \
  --timeout-keep-alive 30
