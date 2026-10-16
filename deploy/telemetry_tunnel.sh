#!/usr/bin/env bash
# Run on your own machine, next to the observability stack
# (observability/docker-compose.yml): opens an SSH tunnel so the lab
# machines can send their telemetry to its OpenTelemetry Collector.
#
#   deploy/telemetry_tunnel.sh -p 2285 student@10.1.75.53
#
# The arguments are passed to ssh, and name the gateway machine. Its
# 127.0.0.1:4318 then leads to the collector here, and the gateway's /otlp/
# path passes on to that, so the API machines export to
# http://<gateway>:<LISTEN_PORT>/otlp without a tunnel of their own.
#
# Reconnects whenever the connection drops. Start it inside tmux so it
# keeps running after the terminal is closed:
#
#   tmux new -d -s telemetry "deploy/telemetry_tunnel.sh -p 2285 student@10.1.75.53"
#
# While it is down the lab machines keep serving requests; only their
# telemetry is lost.
set -uo pipefail

if [ "$#" -eq 0 ]; then
    echo "usage: $0 [ssh options] USER@GATEWAY" >&2
    exit 1
fi

while true; do
    echo "$(date '+%F %T') connecting: $*"
    ssh -N \
        -o ExitOnForwardFailure=yes \
        -o ServerAliveInterval=15 \
        -o ServerAliveCountMax=3 \
        -R 127.0.0.1:4318:127.0.0.1:4318 \
        "$@"
    echo "$(date '+%F %T') tunnel closed, reconnecting in 5 s"
    sleep 5
done
