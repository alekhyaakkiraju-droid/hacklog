"""Unit and integration tests for hacklog.security."""

from __future__ import annotations

import socket
import threading
import time

import pytest

from hacklog.metrics import messages_dropped_total, messages_received_total
from hacklog.security import (
    IpAllowlist,
    MessageValidator,
    RateLimiter,
    TokenBucket,
    build_message_validator,
    parse_allowed_cidrs,
)


@pytest.fixture
def metered_validator() -> MessageValidator:
    return MessageValidator(
        allowlist=IpAllowlist(["10.0.0.0/8"]),
        max_message_size=2048,
        rate_limiter=RateLimiter(rate_per_second=100, burst_capacity=100),
        meter_and_log=True,
    )


def test_rejected_messages_increment_prometheus_counter(metered_validator: MessageValidator) -> None:
    before = messages_dropped_total.labels(reason="ip_rejected")._value.get()  # noqa: SLF001
    metered_validator.validate("203.0.113.5", b"drop-me")
    after = messages_dropped_total.labels(reason="ip_rejected")._value.get()  # noqa: SLF001
    assert after - before == 1.0


def test_accepted_messages_increment_received_counter() -> None:
    before = messages_received_total._value.get()  # noqa: SLF001
    validator = MessageValidator(
        allowlist=IpAllowlist([]),
        max_message_size=2048,
        rate_limiter=RateLimiter(rate_per_second=100, burst_capacity=100),
        meter_and_log=True,
    )
    validator.validate("10.0.0.5", b"accepted")
    after = messages_received_total._value.get()  # noqa: SLF001
    assert after - before == 1.0


def test_parse_allowed_cidrs_splits_comma_separated_values() -> None:
    assert parse_allowed_cidrs("10.0.0.0/8, 192.168.0.0/16") == [
        "10.0.0.0/8",
        "192.168.0.0/16",
    ]


def test_build_message_validator_reads_env_allowed_cidrs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HACKLOG_ALLOWED_CIDRS", "192.168.0.0/16")
    validator = build_message_validator(meter_and_log=False)
    assert validator.validate("192.168.1.10", b"x").accepted is True
    assert validator.validate("10.1.1.1", b"x").accepted is False


def test_empty_allowlist_accepts_all_ips() -> None:
    allowlist = IpAllowlist([])
    assert allowlist.is_allowed("10.42.10.2") is True
    assert allowlist.is_allowed("203.0.113.5") is True


def test_allowlisted_ip_is_accepted() -> None:
    validator = MessageValidator(
        allowlist=IpAllowlist(["10.0.0.0/8"]),
        max_message_size=2048,
        rate_limiter=RateLimiter(rate_per_second=100, burst_capacity=100),
        meter_and_log=False,
    )
    result = validator.validate("10.42.10.2", b"ok")
    assert result.accepted is True


def test_non_allowlisted_ip_is_rejected() -> None:
    validator = MessageValidator(
        allowlist=IpAllowlist(["10.0.0.0/8"]),
        max_message_size=2048,
        rate_limiter=RateLimiter(rate_per_second=100, burst_capacity=100),
        meter_and_log=False,
    )
    result = validator.validate("203.0.113.5", b"bad")
    assert result.accepted is False
    assert result.reason == "ip_rejected"


def test_cidr_range_matching() -> None:
    allowlist = IpAllowlist(["10.0.0.0/8"])
    assert allowlist.is_allowed("10.42.10.2") is True
    assert allowlist.is_allowed("11.0.0.1") is False


def test_oversized_message_is_rejected() -> None:
    validator = MessageValidator(
        allowlist=IpAllowlist([]),
        max_message_size=32,
        rate_limiter=RateLimiter(rate_per_second=100, burst_capacity=100),
        meter_and_log=False,
    )
    result = validator.validate("10.0.0.1", b"x" * 33)
    assert result.accepted is False
    assert result.reason == "oversized"


def test_rate_limited_source_is_rejected_after_burst() -> None:
    validator = MessageValidator(
        allowlist=IpAllowlist([]),
        max_message_size=2048,
        rate_limiter=RateLimiter(rate_per_second=5, burst_capacity=2),
        meter_and_log=False,
    )
    assert validator.validate("10.0.0.9", b"a").accepted is True
    assert validator.validate("10.0.0.9", b"b").accepted is True
    result = validator.validate("10.0.0.9", b"c")
    assert result.accepted is False
    assert result.reason == "rate_limited"


def test_token_bucket_refills_over_time() -> None:
    bucket = TokenBucket(rate_per_second=10, burst_capacity=1)
    assert bucket.consume() is True
    assert bucket.consume() is False
    time.sleep(0.2)
    assert bucket.consume() is True


def test_rate_limiter_isolates_sources() -> None:
    limiter = RateLimiter(rate_per_second=1, burst_capacity=1)
    assert limiter.allow("10.0.0.1") is True
    assert limiter.allow("10.0.0.1") is False
    assert limiter.allow("10.0.0.2") is True


def test_udp_integration_accepts_and_rejects_datagrams() -> None:
    validator = MessageValidator(
        allowlist=IpAllowlist(["127.0.0.0/8"]),
        max_message_size=2048,
        rate_limiter=RateLimiter(rate_per_second=100, burst_capacity=100),
        meter_and_log=False,
    )
    accepted: list[tuple[str, bytes]] = []
    rejected: list[tuple[str, str]] = []
    stop_event = threading.Event()

    def serve() -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 0))
        sock.settimeout(0.2)
        port = sock.getsockname()[1]
        serve.port = port  # type: ignore[attr-defined]
        while not stop_event.is_set():
            try:
                payload, (host, _port) = sock.recvfrom(4096)
            except socket.timeout:
                continue
            result = validator.validate(host, payload)
            if result.accepted:
                accepted.append((host, payload))
            else:
                rejected.append((host, result.reason or "unknown"))

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    while not hasattr(serve, "port"):
        time.sleep(0.01)
    port = serve.port  # type: ignore[attr-defined]

    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client.sendto(b"allowed", ("127.0.0.1", port))
    client.sendto(b"x" * 3000, ("127.0.0.1", port))
    time.sleep(0.3)
    stop_event.set()
    thread.join(timeout=1)

    assert any(payload == b"allowed" for _host, payload in accepted)
    assert any(reason == "oversized" for _host, reason in rejected)
