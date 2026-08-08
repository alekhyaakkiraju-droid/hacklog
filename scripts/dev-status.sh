#!/bin/sh
# Report whether the local Hacklog dev server is running.

set -eu

ROOT="$(CDPATH= cd "$(dirname "$0")/.." && pwd)"
PIDFILE="${HACKLOG_PIDFILE:-$ROOT/.hacklog-dev.pid}"

if [ ! -f "$PIDFILE" ]; then
    echo "hacklog is stopped (no pid file)"
    exit 1
fi

PID="$(cat "$PIDFILE")"
if kill -0 "$PID" 2>/dev/null; then
    echo "hacklog is running (pid $PID)"
    exit 0
fi

echo "hacklog is stopped (stale pid file for $PID)"
exit 1
