"""Network-layer syslog ingestion security controls."""

import ipaddress
import os
import threading
import time
from dataclasses import dataclass

try:
    from hacklog.logging_config import get_logger
    from hacklog.metrics import messages_dropped_total, messages_received_total
except ImportError:
    from logging_config import get_logger
    from metrics import messages_dropped_total, messages_received_total

logger = get_logger("security")

@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating an incoming syslog datagram."""

    accepted: bool
    reason: str | None = None

def parse_allowed_cidrs(raw_value: str | None) -> list[str]:
    """Parse comma-separated CIDR values from configuration."""
    if not raw_value or not raw_value.strip():
        return []
    return [entry.strip() for entry in raw_value.split(",") if entry.strip()]

def allowed_cidrs_from_env() -> list[str]:
    """Load allowlisted CIDRs from HACKLOG_ALLOWED_CIDRS."""
    return parse_allowed_cidrs(os.environ.get("HACKLOG_ALLOWED_CIDRS"))

class IpAllowlist:
    """CIDR-based source IP allowlist."""

    def __init__(self, cidrs: list[str] | None = None) -> None:
        self._networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        for cidr in cidrs or []:
            self._networks.append(ipaddress.ip_network(cidr, strict=False))

    def is_allowed(self, source_ip: str) -> bool:
        if not self._networks:
            return True
        try:
            address = ipaddress.ip_address(source_ip)
        except ValueError:
            return False
        return any(address in network for network in self._networks)

class TokenBucket:
    """Token bucket used for per-source rate limiting."""

    def __init__(self, rate_per_second: float, burst_capacity: int) -> None:
        self.rate_per_second = rate_per_second
        self.burst_capacity = burst_capacity
        self.tokens = float(burst_capacity)
        self.last_refill = time.monotonic()

    def consume(self, amount: int = 1) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(
            self.burst_capacity, self.tokens + elapsed * self.rate_per_second
        )
        self.last_refill = now
        if self.tokens >= amount:
            self.tokens -= amount
            return True
        return False

class RateLimiter:
    """Thread-safe per-source token bucket rate limiter with TTL cleanup."""

    def __init__(
        self,
        rate_per_second: float,
        burst_capacity: int | None = None,
        ttl_seconds: float = 300.0,
    ) -> None:
        self.rate_per_second = rate_per_second
        self.burst_capacity = (
            burst_capacity if burst_capacity is not None else int(rate_per_second)
        )
        self.ttl_seconds = ttl_seconds
        self._buckets: dict[str, tuple[TokenBucket, float]] = {}
        self._lock = threading.Lock()

    def allow(self, source_ip: str) -> bool:
        now = time.monotonic()
        with self._lock:
            self._cleanup_expired(now)
            bucket, _last_seen = self._buckets.get(source_ip, (None, now))
            if bucket is None:
                bucket = TokenBucket(self.rate_per_second, self.burst_capacity)
            allowed = bucket.consume()
            self._buckets[source_ip] = (bucket, now)
            return allowed

    def _cleanup_expired(self, now: float) -> None:
        expired = [
            source_ip
            for source_ip, (_, last_seen) in self._buckets.items()
            if now - last_seen > self.ttl_seconds
        ]
        for source_ip in expired:
            del self._buckets[source_ip]

class MessageValidator:
    """Validate syslog datagrams before they enter the processing queue."""

    def __init__(
        self,
        allowlist: IpAllowlist,
        max_message_size: int,
        rate_limiter: RateLimiter,
        meter_and_log: bool = True,
    ) -> None:
        self.allowlist = allowlist
        self.max_message_size = max_message_size
        self.rate_limiter = rate_limiter
        self.meter_and_log = meter_and_log

    def validate(self, source_ip: str, payload: bytes) -> ValidationResult:
        if not self.allowlist.is_allowed(source_ip):
            return self._reject(source_ip, "ip_rejected", len(payload))
        if len(payload) > self.max_message_size:
            return self._reject(source_ip, "oversized", len(payload))
        if not self.rate_limiter.allow(source_ip):
            return self._reject(source_ip, "rate_limited", len(payload))

        if self.meter_and_log:
            messages_received_total.inc()
        return ValidationResult(accepted=True)

    def _reject(
        self, source_ip: str, reason: str, message_size: int
    ) -> ValidationResult:
        if self.meter_and_log:
            messages_dropped_total.labels(reason=reason).inc()
            logger.warning(
                "message_dropped",
                operation="validate_datagram",
                source_ip=source_ip,
                reason=reason,
                message_size=message_size,
            )
        return ValidationResult(accepted=False, reason=reason)

def build_message_validator(
    allowed_cidrs: list[str] | None = None,
    max_message_size: int = 2048,
    rate_per_second: float = 100.0,
    burst_capacity: int | None = None,
    meter_and_log: bool = True,
) -> MessageValidator:
    """Construct a MessageValidator from syslog security settings."""
    cidrs = allowed_cidrs if allowed_cidrs is not None else allowed_cidrs_from_env()
    return MessageValidator(
        allowlist=IpAllowlist(cidrs),
        max_message_size=max_message_size,
        rate_limiter=RateLimiter(rate_per_second, burst_capacity=burst_capacity),
        meter_and_log=meter_and_log,
    )
