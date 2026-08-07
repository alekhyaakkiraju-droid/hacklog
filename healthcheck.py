#!/usr/bin/env python3
"""Docker health check for hacklog: verifies the syslog UDP port is bound."""
import os
import socket
import sys

port = int(os.environ.get("HACKLOG_SYSLOG_PORT", "10514"))
# Bind to loopback to probe whether the syslog port is already in use.
# If the server listens on 0.0.0.0 or 127.0.0.1, this bind attempt conflicts.
bind_addr = "127.0.0.1"

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    s.bind((bind_addr, port))
    # Successfully bound → port is free → server is NOT running → unhealthy
    s.close()
    sys.exit(1)
except OSError:
    # Could not bind → port already in use → server IS running → healthy
    sys.exit(0)
