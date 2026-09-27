#!/usr/bin/env bash
# Start the analysis API on one backend machine.
#
#   deploy/run_api.sh              # port 8000, one worker
#   PORT=5288 WORKERS=2 deploy/run_api.sh
#
# The defaults suit the 512 MB lab machines: one worker process (~100 MB
# idle, ~300 MB while analyzing) handling one analysis at a time. On a
# machine with more memory, raise WORKERS (each worker is a separate
# process, so analyses on different workers run in parallel). The limits in
# docs/API.md can be set in the environment as well.
set -euo pipefail

cd "$(dirname "$0")/.."
source venv/bin/activate

PORT="${PORT:-8000}"
WORKERS="${WORKERS:-1}"

# Keep the numeric libraries single-threaded (each extra thread reserves its
# own buffers) and limit glibc's per-thread malloc arenas, which otherwise
# hold on to freed memory between requests.
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export MALLOC_ARENA_MAX="${MALLOC_ARENA_MAX:-2}"

exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --workers "$WORKERS" \
  --timeout-keep-alive 30
