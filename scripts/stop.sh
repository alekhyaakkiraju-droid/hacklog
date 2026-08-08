#!/bin/sh
# Stop the locally running Hacklog server with graceful SIGTERM shutdown.
#
# The server handles SIGTERM/SIGINT and releases database resources before exit
# (see hacklog/syslog_server.py and hacklog/server.py).
#
# Usage:
#   ./scripts/stop.sh
#   make dev-stop

set -eu

ROOT="$(CDPATH= cd "$(dirname "$0")/.." && pwd)"
PIDFILE="${HACKLOG_PIDFILE:-$ROOT/.hacklog-dev.pid}"
TIMEOUT="${HACKLOG_STOP_TIMEOUT:-30}"

if [ ! -f "$PIDFILE" ]; then
    echo "hacklog is not running (no pid file at $PIDFILE)"
    exit 0
fi

PID="$(cat "$PIDFILE")"

if ! kill -0 "$PID" 2>/dev/null; then
    echo "Removing stale pid file (process $PID is not running)"
    rm -f "$PIDFILE"
    exit 0
fi

echo "Sending SIGTERM to hacklog (pid $PID) for graceful shutdown..."
kill -TERM "$PID"

elapsed=0
while kill -0 "$PID" 2>/dev/null; do
    if [ "$elapsed" -ge "$TIMEOUT" ]; then
        echo "Timed out after ${TIMEOUT}s waiting for graceful shutdown." >&2
        echo "The process may still be running; investigate pid $PID manually." >&2
        exit 1
    fi
    sleep 1
    elapsed=$((elapsed + 1))
done

rm -f "$PIDFILE"
echo "hacklog stopped gracefully"
