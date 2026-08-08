#!/bin/sh
# Start the Hacklog syslog server for local development.
#
# Configuration is loaded from:
#   1. HACKLOG_* environment variables (pydantic-settings / ConfigManager)
#   2. conf/server.conf (legacy bind/port and parser patterns)
#
# Usage:
#   cp .env.example .env   # set required SMTP secrets
#   ./scripts/run.sh
#   make dev-start

set -eu

ROOT="$(CDPATH= cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PIDFILE="${HACKLOG_PIDFILE:-$ROOT/.hacklog-dev.pid}"
LOGFILE="${HACKLOG_LOGFILE:-$ROOT/var/log/hacklog-dev.log}"
CONFIG="${HACKLOG_CONFIG:-$ROOT/conf/server.conf}"
PYTHON="${PYTHON:-python3}"

if [ -f "$PIDFILE" ]; then
    OLD_PID="$(cat "$PIDFILE")"
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "hacklog is already running (pid $OLD_PID). Run ./scripts/stop.sh first." >&2
        exit 1
    fi
    rm -f "$PIDFILE"
fi

if [ -f "$ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$ROOT/.env"
    set +a
fi

if [ -z "${HACKLOG_SMTP_USER:-}" ] || [ -z "${HACKLOG_SMTP_PASSWORD:-}" ]; then
    echo "Missing required HACKLOG_SMTP_* settings." >&2
    echo "Copy .env.example to .env and set SMTP credentials for ConfigManager." >&2
    exit 1
fi

export HACKLOG_DATABASE_DB_URL="${HACKLOG_DATABASE_DB_URL:-sqlite:///$ROOT/hacklog.db}"

if [ ! -f "$CONFIG" ]; then
    echo "Configuration file not found: $CONFIG" >&2
    exit 1
fi

mkdir -p "$(dirname "$LOGFILE")"

nohup "$PYTHON" "$ROOT/hacklog/server.py" -c "$CONFIG" >>"$LOGFILE" 2>&1 &
echo $! >"$PIDFILE"

echo "Started hacklog (pid $(cat "$PIDFILE"))"
echo "  config: $CONFIG"
echo "  log:    $LOGFILE"
echo "  env:    HACKLOG_* variables via ConfigManager (see hacklog/config.py)"
