"""Prometheus metrics definitions and exposition for hacklog."""

from __future__ import annotations

import os
import socket
import threading
from typing import Any

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from prometheus_client import start_http_server as _prometheus_start_http_server

messages_received_total = Counter(
    "messages_received_total",
    "Total syslog messages received by the UDP listener.",
)

messages_dropped_total = Counter(
    "messages_dropped_total",
    "Total syslog messages dropped before processing.",
    ["reason"],
)

messages_parsed_total = Counter(
    "messages_parsed_total",
    "Total syslog messages parsed.",
    ["format", "status"],
)

scoring_duration_seconds = Histogram(
    "scoring_duration_seconds",
    "Latency of anomaly score calculation in seconds.",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

scores_calculated_total = Counter(
    "scores_calculated_total",
    "Total anomaly scores calculated.",
    ["decision"],
)

alerts_sent_total = Counter(
    "alerts_sent_total",
    "Total alert notification attempts.",
    ["status"],
)

queue_depth = Gauge(
    "queue_depth",
    "Current syslog message queue depth.",
)

db_operation_duration_seconds = Histogram(
    "db_operation_duration_seconds",
    "Database operation latency in seconds.",
    ["operation"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

_server_lock = threading.Lock()
_server_started = False
_server_port: int | None = None


def metrics_enabled(enabled: bool | None = None) -> bool:
    """Return whether the metrics HTTP server should be enabled."""
    if enabled is not None:
        return enabled
    value = os.environ.get("HACKLOG_METRICS_ENABLED", "false").strip().lower()
    return value in {"1", "true", "yes", "on"}


def metrics_port(port: int | None = None) -> int:
    """Return the configured metrics HTTP port."""
    if port is not None:
        return port
    raw_port = os.environ.get("HACKLOG_METRICS_PORT", "9090")
    return int(raw_port)


def render_metrics() -> bytes:
    """Render all registered metrics in Prometheus exposition format."""
    return generate_latest()


def find_available_port() -> int:
    """Find an available TCP port for the metrics HTTP server."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_metrics_server(
    port: int | None = None, enabled: bool | None = None
) -> int | None:
    """Start the Prometheus /metrics HTTP server when enabled."""
    global _server_started, _server_port

    if not metrics_enabled(enabled):
        return None

    selected_port = port if port is not None else metrics_port()

    with _server_lock:
        if _server_started:
            return _server_port

        _prometheus_start_http_server(selected_port, addr="127.0.0.1")
        _server_started = True
        _server_port = selected_port
        return selected_port


def reset_metrics_server_state_for_testing() -> None:
    """Reset module-level server state between tests."""
    global _server_started, _server_port
    with _server_lock:
        _server_started = False
        _server_port = None


def get_metric_objects() -> dict[str, Any]:
    """Return the defined metric objects for validation and testing."""
    return {
        "messages_received_total": messages_received_total,
        "messages_dropped_total": messages_dropped_total,
        "messages_parsed_total": messages_parsed_total,
        "scoring_duration_seconds": scoring_duration_seconds,
        "scores_calculated_total": scores_calculated_total,
        "alerts_sent_total": alerts_sent_total,
        "queue_depth": queue_depth,
        "db_operation_duration_seconds": db_operation_duration_seconds,
    }


METRICS_CONTENT_TYPE = CONTENT_TYPE_LATEST
