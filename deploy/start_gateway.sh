#!/usr/bin/env bash
# Start nginx in front of the API machines, serving the built frontend.
#
#   deploy/start_gateway.sh 10.1.75.53:8000 10.1.75.54:8000 10.1.75.55:8000 10.1.75.56:8000
#
# Build the frontend first on a machine with more memory (npm needs far
# more than the lab machines' 512 MB) and copy frontend/dist over:
#
#   cd frontend && npm ci && npm run build
#
# LISTEN_PORT (default 8080) is where the app is served. Browser traces are
# passed on to the OpenTelemetry Collector at OTLP_TARGET (default
# 127.0.0.1:4318). nginx runs in the foreground, so start this inside tmux
# (or with nohup); Ctrl-C stops it.
set -euo pipefail

if [ "$#" -eq 0 ]; then
    echo "usage: $0 HOST:PORT [HOST:PORT ...]" >&2
    exit 1
fi

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
LISTEN_PORT="${LISTEN_PORT:-8080}"
OTLP_TARGET="${OTLP_TARGET:-127.0.0.1:4318}"

servers=""
for server in "$@"; do
    servers+="        server ${server} max_fails=3 fail_timeout=10s;"$'\n'
done

if [ ! -f "$DEPLOY_DIR/../frontend/dist/index.html" ]; then
    echo "frontend/dist is missing: build it with 'npm ci && npm run build' in frontend/ and copy it here" >&2
    exit 1
fi

# nginx treats SIGHUP (e.g. its tmux session being closed) as "reload",
# not "exit", so a gateway from an earlier run can still hold the port.
# Shut it down cleanly before starting again.
if [ -f "$DEPLOY_DIR/nginx.pid" ] && kill -0 "$(cat "$DEPLOY_DIR/nginx.pid")" 2>/dev/null; then
    echo "Stopping the gateway already running (pid $(cat "$DEPLOY_DIR/nginx.pid"))"
    kill -QUIT "$(cat "$DEPLOY_DIR/nginx.pid")"
    while kill -0 "$(cat "$DEPLOY_DIR/nginx.pid" 2>/dev/null)" 2>/dev/null; do sleep 0.2; done
fi

mkdir -p "$DEPLOY_DIR/logs"
awk -v servers="${servers%$'\n'}" -v port="$LISTEN_PORT" -v otlp="$OTLP_TARGET" '
    /__API_SERVERS__/ { print servers; next }
    { gsub(/__LISTEN_PORT__/, port); gsub(/__OTLP_TARGET__/, otlp); print }
' "$DEPLOY_DIR/nginx.conf.template" > "$DEPLOY_DIR/nginx.generated.conf"

# -e: the packaged default error log path isn't writable without root
nginx -p "$DEPLOY_DIR" -e logs/error.log -c nginx.generated.conf -t
echo "Serving on port $LISTEN_PORT, balancing across: $*"
exec nginx -p "$DEPLOY_DIR" -e logs/error.log -c nginx.generated.conf -g "daemon off;"
