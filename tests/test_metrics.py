"""Unit tests for hacklog.metrics."""

from __future__ import annotations

import re
import urllib.error
import urllib.request

import pytest

from hacklog.metrics import (
    alerts_sent_total,
    db_operation_duration_seconds,
    find_available_port,
    get_metric_objects,
    messages_dropped_total,
    messages_parsed_total,
    messages_received_total,
    metrics_enabled,
    queue_depth,
    render_metrics,
    reset_metrics_server_state_for_testing,
    scores_calculated_total,
    scoring_duration_seconds,
    start_metrics_server,
)


@pytest.fixture(autouse=True)
def reset_metrics_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HACKLOG_METRICS_ENABLED", raising=False)
    monkeypatch.delenv("HACKLOG_METRICS_PORT", raising=False)
    reset_metrics_server_state_for_testing()


def test_metric_objects_are_defined() -> None:
    metrics = get_metric_objects()
    assert set(metrics) == {
        "messages_received_total",
        "messages_dropped_total",
        "messages_parsed_total",
        "scoring_duration_seconds",
        "scores_calculated_total",
        "alerts_sent_total",
        "queue_depth",
        "db_operation_duration_seconds",
    }


def test_metrics_can_be_incremented_and_observed() -> None:
    messages_received_total.inc()
    messages_dropped_total.labels(reason="rate_limit").inc()
    messages_parsed_total.labels(format="syslog", status="success").inc()
    scores_calculated_total.labels(decision="alert").inc()
    scores_calculated_total.labels(decision="normal").inc()
    alerts_sent_total.labels(status="success").inc()
    alerts_sent_total.labels(status="failure").inc()
    queue_depth.set(7)

    scoring_duration_seconds.observe(0.012)
    db_operation_duration_seconds.labels(operation="save").observe(0.004)

    output = render_metrics().decode("utf-8")
    assert "messages_received_total" in output
    assert 'messages_dropped_total{reason="rate_limit"}' in output
    assert 'messages_parsed_total{format="syslog",status="success"}' in output
    assert 'scores_calculated_total{decision="alert"}' in output
    assert 'scores_calculated_total{decision="normal"}' in output
    assert 'alerts_sent_total{status="success"}' in output
    assert 'alerts_sent_total{status="failure"}' in output
    assert "queue_depth" in output
    assert "scoring_duration_seconds" in output
    assert 'operation="save"' in output
    assert "db_operation_duration_seconds_bucket" in output


def test_render_metrics_returns_prometheus_exposition_format() -> None:
    messages_received_total.inc(3)
    output = render_metrics().decode("utf-8")

    assert re.search(r"^# HELP messages_received_total ", output, re.MULTILINE)
    assert re.search(r"^# TYPE messages_received_total counter", output, re.MULTILINE)
    assert re.search(r"^messages_received_total ", output, re.MULTILINE)


def test_metrics_server_disabled_by_default() -> None:
    assert metrics_enabled() is False
    assert start_metrics_server(port=find_available_port()) is None


def test_metrics_server_can_be_disabled_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HACKLOG_METRICS_ENABLED", "false")
    assert start_metrics_server(port=find_available_port(), enabled=None) is None


def test_metrics_endpoint_returns_prometheus_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = find_available_port()
    monkeypatch.setenv("HACKLOG_METRICS_ENABLED", "true")

    started_port = start_metrics_server(port=port)
    assert started_port == port

    messages_received_total.inc(2)
    queue_depth.set(4)

    with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=2) as response:
        body = response.read().decode("utf-8")
        content_type = response.headers.get("Content-Type", "")

    assert "text/plain" in content_type
    assert "messages_received_total" in body
    assert "queue_depth" in body
    assert re.search(r"^# HELP ", body, re.MULTILINE)
    assert re.search(r"^# TYPE ", body, re.MULTILINE)


def test_metrics_endpoint_not_available_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = find_available_port()
    monkeypatch.setenv("HACKLOG_METRICS_ENABLED", "false")

    assert start_metrics_server(port=port) is None

    with pytest.raises(urllib.error.URLError):
        urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=1)
