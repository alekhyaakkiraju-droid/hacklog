"""Unit tests for AlertService, CircuitBreaker, and retry logic."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from aiosmtplib.errors import SMTPAuthenticationError, SMTPConnectError
from pydantic import SecretStr

_TESTS_DIR = Path(__file__).resolve().parent
_HACKLOG_DIR = _TESTS_DIR.parent / "hacklog"
for _path in (_TESTS_DIR, _HACKLOG_DIR, _TESTS_DIR.parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from alerting import (  # noqa: E402
    AlertService,
    CircuitBreaker,
    CircuitState,
    DeadLetterWriter,
    build_alert_message,
    is_transient_smtp_error,
)
from entities import EventLog, User  # noqa: E402

try:
    from hacklog.config import SmtpConfig
except ImportError:
    from config import SmtpConfig


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.current = start

    def __call__(self) -> float:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += seconds


@pytest.fixture
def smtp_config() -> SmtpConfig:
    return SmtpConfig(
        host="smtp.example.com",
        port=587,
        username="test@example.com",
        password=SecretStr("test-password"),
        sender="alerts@example.com",
        recipient="soc@example.com",
        use_tls=True,
    )


@pytest.fixture
def event_log() -> EventLog:
    return EventLog(datetime(2026, 1, 15, 10, 30, 0), "nrhine", "10.0.0.1", False, "prod-host")


@pytest.fixture
def user() -> User:
    return User("nrhine", datetime(2026, 1, 15, 10, 30, 0), 75)


@pytest.fixture
def dead_letter_path(tmp_path: Path) -> Path:
    return tmp_path / "dead_letter.jsonl"


@pytest.fixture
def success_smtp_sender() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def transient_failure_smtp_sender() -> AsyncMock:
    sender = AsyncMock(
        side_effect=[
            SMTPConnectError("connection reset"),
            SMTPConnectError("connection reset"),
            None,
        ]
    )
    return sender


@pytest.fixture
def permanent_failure_smtp_sender() -> AsyncMock:
    sender = AsyncMock(side_effect=SMTPAuthenticationError(535, "invalid credentials"))
    return sender


@pytest.mark.asyncio
async def test_circuit_breaker_closed_to_open_after_five_failures() -> None:
    breaker = CircuitBreaker(failure_threshold=5)
    for _ in range(4):
        await breaker.record_failure()
        assert breaker.state == CircuitState.CLOSED

    await breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    assert not await breaker.allow_request()


@pytest.mark.asyncio
async def test_circuit_breaker_open_to_half_open_after_timeout() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout=60.0, clock=clock)
    await breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    assert not await breaker.allow_request()

    clock.advance(60.0)
    assert await breaker.allow_request()
    assert breaker.state == CircuitState.HALF_OPEN


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_to_closed_on_success() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout=60.0, clock=clock)
    await breaker.record_failure()
    clock.advance(60.0)
    assert await breaker.allow_request()
    await breaker.record_success()
    assert breaker.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_rejects_second_probe() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout=60.0, clock=clock)
    await breaker.record_failure()
    clock.advance(60.0)
    assert await breaker.allow_request()
    assert not await breaker.allow_request()


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_to_open_on_probe_failure() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout=60.0, clock=clock)
    await breaker.record_failure()
    clock.advance(60.0)
    assert await breaker.allow_request()
    await breaker.record_failure()
    assert breaker.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_alert_service_retries_transient_failure(
    smtp_config: SmtpConfig,
    user: User,
    event_log: EventLog,
    transient_failure_smtp_sender: AsyncMock,
    dead_letter_path: Path,
) -> None:
    service = AlertService(
        smtp_config,
        smtp_sender=transient_failure_smtp_sender,
        dead_letter_path=dead_letter_path,
        retry_base_delay_seconds=0.01,
    )
    await service.send_alert(user, event_log)
    assert transient_failure_smtp_sender.await_count == 3
    assert not dead_letter_path.exists()


@pytest.mark.asyncio
async def test_alert_service_does_not_retry_permanent_failure(
    smtp_config: SmtpConfig,
    user: User,
    event_log: EventLog,
    permanent_failure_smtp_sender: AsyncMock,
    dead_letter_path: Path,
) -> None:
    service = AlertService(
        smtp_config,
        smtp_sender=permanent_failure_smtp_sender,
        dead_letter_path=dead_letter_path,
        retry_base_delay_seconds=0.01,
    )
    await service.send_alert(user, event_log)
    assert permanent_failure_smtp_sender.await_count == 1
    assert dead_letter_path.exists()
    payload = json.loads(dead_letter_path.read_text(encoding="utf-8").strip())
    assert payload["username"] == user.username
    assert payload["server"] == event_log.server


@pytest.mark.asyncio
async def test_alert_service_success_logs_and_closes_circuit(
    smtp_config: SmtpConfig,
    user: User,
    event_log: EventLog,
    success_smtp_sender: AsyncMock,
) -> None:
    breaker = CircuitBreaker(failure_threshold=5)
    service = AlertService(
        smtp_config,
        circuit_breaker=breaker,
        smtp_sender=success_smtp_sender,
    )
    await service.send_alert(user, event_log)
    success_smtp_sender.assert_awaited_once()
    assert breaker.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_alert_service_writes_dead_letter_when_circuit_open(
    smtp_config: SmtpConfig,
    user: User,
    event_log: EventLog,
    dead_letter_path: Path,
) -> None:
    breaker = CircuitBreaker(failure_threshold=1)
    await breaker.record_failure()
    service = AlertService(
        smtp_config,
        circuit_breaker=breaker,
        dead_letter_path=dead_letter_path,
        smtp_sender=AsyncMock(),
    )
    await service.send_alert(user, event_log)
    assert dead_letter_path.exists()
    payload = json.loads(dead_letter_path.read_text(encoding="utf-8").strip())
    assert payload["reason"] == "circuit_open"


def test_build_alert_message_includes_required_fields(user: User, event_log: EventLog) -> None:
    message = build_alert_message(
        user,
        event_log,
        sender="alerts@example.com",
        recipient="soc@example.com",
    )
    body = message.get_payload()[0].get_payload()
    assert user.username in body
    assert event_log.server in body
    assert str(user.score) in body
    assert "2026-01-15" in body


def test_is_transient_smtp_error_classification() -> None:
    assert is_transient_smtp_error(SMTPConnectError("timeout"))
    assert not is_transient_smtp_error(SMTPAuthenticationError(535, "bad auth"))


@pytest.mark.asyncio
async def test_dead_letter_writer_rotates_when_max_size_exceeded(tmp_path: Path) -> None:
    path = tmp_path / "dead_letter.jsonl"
    writer = DeadLetterWriter(path, max_bytes=32)
    await writer.write({"username": "a", "server": "s1", "score": 1, "timestamp": "t"})
    await writer.write({"username": "b", "server": "s2", "score": 2, "timestamp": "t"})
    assert path.exists()
    rotated_files = list(tmp_path.glob("dead_letter.*.jsonl"))
    assert len(rotated_files) == 1


def test_send_email_alert_sync_wrapper(
    smtp_config: SmtpConfig,
    user: User,
    event_log: EventLog,
) -> None:
    sender = AsyncMock()
    service = AlertService(smtp_config, smtp_sender=sender)
    service.sendEmailAlert(user, event_log)
    sender.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_email_alert_schedules_task_in_running_loop(
    smtp_config: SmtpConfig,
    user: User,
    event_log: EventLog,
) -> None:
    sender = AsyncMock()
    service = AlertService(smtp_config, smtp_sender=sender)
    service.sendEmailAlert(user, event_log)
    await asyncio.sleep(0)
    sender.assert_awaited_once()
