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
# LISTEN_PORT (default 8080) is where the app is served. Stop the gateway
# with: nginx -p "$PWD/deploy" -c nginx.generated.conf -s stop
set -euo pipefail

if [ "$#" -eq 0 ]; then
    echo "usage: $0 HOST:PORT [HOST:PORT ...]" >&2
    exit 1
fi

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
LISTEN_PORT="${LISTEN_PORT:-8080}"

servers=""
for server in "$@"; do
    servers+="        server ${server} max_fails=3 fail_timeout=10s;"$'\n'
done

if [ ! -f "$DEPLOY_DIR/../frontend/dist/index.html" ]; then
    echo "frontend/dist is missing: build it with 'npm ci && npm run build' in frontend/ and copy it here" >&2
    exit 1
fi

mkdir -p "$DEPLOY_DIR/logs"
awk -v servers="${servers%$'\n'}" -v port="$LISTEN_PORT" '
    /__API_SERVERS__/ { print servers; next }
    { gsub(/__LISTEN_PORT__/, port); print }
' "$DEPLOY_DIR/nginx.conf.template" > "$DEPLOY_DIR/nginx.generated.conf"

nginx -p "$DEPLOY_DIR" -c nginx.generated.conf -t
nginx -p "$DEPLOY_DIR" -c nginx.generated.conf
echo "Serving on port $LISTEN_PORT, balancing across: $*"
