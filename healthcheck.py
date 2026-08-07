#!/usr/bin/env python3
"""Docker health check for hacklog: verifies the syslog UDP port is bound."""
import os
import socket
import sys

port = int(os.environ.get("HACKLOG_SYSLOG_PORT", "10514"))
# Use the same bind address as the server to guarantee a conflict.
# Defaults to 0.0.0.0 (wildcard), which conflicts whether the server is
# listening on 0.0.0.0 or on a specific address such as 127.0.0.1.
bind_addr = os.environ.get("HACKLOG_SYSLOG_BIND_ADDRESS", "0.0.0.0")

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    s.bind((bind_addr, port))
    # Successfully bound → port is free → server is NOT running → unhealthy
    s.close()
    sys.exit(1)
except OSError:
    # Could not bind → port already in use → server IS running → healthy
    sys.exit(0)
