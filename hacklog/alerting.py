"""Async alert delivery with circuit breaker, retry, and dead letter queue."""

import asyncio
import json
import os
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from pathlib import Path
from typing import Any

import aiosmtplib
from aiosmtplib.errors import SMTPAuthenticationError, SMTPConnectError, SMTPException

try:
    from config import SmtpConfig
    from entities import AuditRecord, EventLog, User
    from logging_config import get_logger
    from repositories import AuditRepository
except ImportError:
    from hacklog.config import SmtpConfig
    from hacklog.entities import AuditRecord, EventLog, User
    from hacklog.logging_config import get_logger
    from hacklog.repositories import AuditRepository

logger = get_logger("alerting")

DEFAULT_DEAD_LETTER_PATH = "dead_letter.jsonl"
DEFAULT_DEAD_LETTER_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_FAILURE_THRESHOLD = 5
DEFAULT_RESET_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_BASE_DELAY_SECONDS = 1.0

SmtpSender = Callable[[MIMEMultipart, SmtpConfig], Awaitable[None]]


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(Exception):
    """Raised when the circuit breaker rejects a request."""


class CircuitBreaker:
    """SMTP circuit breaker with closed, open, and half-open states."""

    def __init__(
        self,
        *,
        failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
        reset_timeout: float = DEFAULT_RESET_TIMEOUT_SECONDS,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._clock = clock or time.monotonic
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at: float | None = None
        self._half_open_probe_in_flight = False
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    async def allow_request(self) -> bool:
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                if (
                    self._opened_at is not None
                    and self._clock() - self._opened_at >= self.reset_timeout
                ):
                    previous = self._state
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_probe_in_flight = False
                    logger.info(
                        "circuit_breaker_state_change",
                        operation="circuit_breaker",
                        previous_state=previous.value,
                        new_state=self._state.value,
                    )
                else:
                    return False

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_probe_in_flight:
                    return False
                self._half_open_probe_in_flight = True
            return True

    async def record_success(self) -> None:
        async with self._lock:
            previous = self._state
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._opened_at = None
                self._half_open_probe_in_flight = False
                logger.info(
                    "circuit_breaker_state_change",
                    operation="circuit_breaker",
                    previous_state=previous.value,
                    new_state=self._state.value,
                )
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0

    async def record_failure(self) -> None:
        async with self._lock:
            previous = self._state
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._opened_at = self._clock()
                self._half_open_probe_in_flight = False
                logger.warning(
                    "circuit_breaker_state_change",
                    operation="circuit_breaker",
                    previous_state=previous.value,
                    new_state=self._state.value,
                    reason="half_open_probe_failed",
                )
                return

            self._failure_count += 1
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = self._clock()
                logger.warning(
                    "circuit_breaker_state_change",
                    operation="circuit_breaker",
                    previous_state=previous.value,
                    new_state=self._state.value,
                    failure_count=self._failure_count,
                )


class DeadLetterWriter:
    """Append failed alerts as JSON lines with size-based rotation."""

    def __init__(
        self,
        path: str | Path = DEFAULT_DEAD_LETTER_PATH,
        *,
        max_bytes: int = DEFAULT_DEAD_LETTER_MAX_BYTES,
    ) -> None:
        self._path = Path(path)
        self._max_bytes = max_bytes
        self._lock = asyncio.Lock()

    @property
    def path(self) -> Path:
        return self._path

    async def write(self, payload: dict[str, Any]) -> None:
        async with self._lock:
            self._rotate_if_needed()
            line = json.dumps(payload, default=str) + "\n"
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(line)
            logger.warning(
                "alert_dead_lettered",
                operation="dead_letter_write",
                path=str(self._path),
                username=payload.get("username"),
                server=payload.get("server"),
            )

    def _rotate_if_needed(self) -> None:
        if not self._path.exists():
            return
        if self._path.stat().st_size < self._max_bytes:
            return
        rotated = self._path.with_suffix(
            f".{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.jsonl"
        )
        self._path.rename(rotated)
        logger.info(
            "dead_letter_rotated",
            operation="dead_letter_rotate",
            previous_path=str(self._path),
            rotated_path=str(rotated),
        )


def _format_alert_timestamp(event_log: EventLog) -> str:
    event_date = event_log.date
    if isinstance(event_date, datetime):
        return event_date.isoformat()
    return str(event_date)


def build_alert_message(
    user: User,
    event_log: EventLog,
    *,
    sender: str,
    recipient: str,
) -> MIMEMultipart:
    timestamp = _format_alert_timestamp(event_log)
    msg = MIMEMultipart()
    msg["Subject"] = "EMAIL ALERT - CONCERNING SSH ACTIVITY ON: " + event_log.server
    msg["From"] = sender
    msg["To"] = recipient
    text = (
        "Hi!\nHow are you?\nThere was some suspicious activity on the following server: "
        + event_log.server
        + " for user: "
        + user.username
        + "\n Their current score is "
        + str(user.score)
        + "\nTimestamp: "
        + timestamp
    )
    msg.attach(MIMEText(text, "plain"))
    return msg


async def default_smtp_sender(message: MIMEMultipart, smtp_config: SmtpConfig) -> None:
    await aiosmtplib.send(
        message,
        hostname=smtp_config.host,
        port=smtp_config.port,
        username=smtp_config.username,
        password=smtp_config.password.get_secret_value(),
        start_tls=smtp_config.use_tls,
    )


def is_transient_smtp_error(exc: BaseException) -> bool:
    if isinstance(exc, (SMTPConnectError, TimeoutError, OSError, ConnectionError)):
        return True
    if isinstance(exc, SMTPException) and not isinstance(exc, SMTPAuthenticationError):
        return True
    return False


class AlertService:
    """Async SMTP alert delivery with circuit breaker and retry logic."""

    def __init__(
        self,
        smtp_config: SmtpConfig | None,
        *,
        circuit_breaker: CircuitBreaker | None = None,
        dead_letter_writer: DeadLetterWriter | None = None,
        smtp_sender: SmtpSender | None = None,
        max_retry_attempts: int = DEFAULT_MAX_RETRY_ATTEMPTS,
        retry_base_delay_seconds: float = DEFAULT_RETRY_BASE_DELAY_SECONDS,
        dead_letter_path: str | Path | None = None,
        audit_repository: AuditRepository | None = None,
    ) -> None:
        if smtp_config is None:
            raise TypeError("AlertService requires SmtpConfig from ConfigManager")
        if not isinstance(smtp_config, SmtpConfig):
            raise TypeError("AlertService requires SmtpConfig from ConfigManager")
        self._smtp_config = smtp_config
        self.from_address = smtp_config.sender
        self.recipient = smtp_config.recipient
        self.mail_server = None
        self._circuit = circuit_breaker or CircuitBreaker()
        if dead_letter_writer is not None:
            self._dead_letter = dead_letter_writer
        else:
            path = dead_letter_path or os.environ.get(
                "HACKLOG_DEAD_LETTER_PATH", DEFAULT_DEAD_LETTER_PATH
            )
            self._dead_letter = DeadLetterWriter(path)
        self._smtp_sender = smtp_sender or default_smtp_sender
        self._max_retry_attempts = max_retry_attempts
        self._retry_base_delay_seconds = retry_base_delay_seconds
        self._audit_repository = audit_repository

    def _emit_audit_record(
        self,
        user: User,
        event_log: EventLog,
        action: str,
        reason: str,
    ) -> None:
        """Emit an audit event as a structured log entry and optionally persist it."""
        timestamp = datetime.now(UTC)
        logger.info(
            "audit_event",
            audit=True,
            actor=user.username,
            action=action,
            source_ip=event_log.ip_address,
            resource=event_log.server,
            outcome=action,
            details={"reason": reason, "score": user.score},
            timestamp=timestamp.isoformat(),
        )
        if self._audit_repository is not None:
            record = AuditRecord(
                timestamp=timestamp,
                actor=user.username,
                source_ip=event_log.ip_address,
                resource=event_log.server,
                action=action,
                outcome=action,
                details={"reason": reason, "score": user.score},
            )
            self._audit_repository.save_audit_record(record)

    async def send_alert(self, user: User, event_log: EventLog) -> None:
        if not await self._circuit.allow_request():
            logger.warning(
                "alert_rejected_circuit_open",
                operation="send_alert",
                username=user.username,
                server=event_log.server,
                circuit_state=self._circuit.state.value,
            )
            await self._dead_letter.write(
                self._dead_letter_payload(user, event_log, reason="circuit_open")
            )
            self._emit_audit_record(user, event_log, "alert_suppressed", "circuit_open")
            return

        logger.info(
            "alert_send_attempt",
            operation="send_alert",
            username=user.username,
            source_ip=event_log.ip_address,
            server=event_log.server,
            score=user.score,
            recipient=self.recipient,
            circuit_state=self._circuit.state.value,
        )

        message = build_alert_message(
            user,
            event_log,
            sender=self.from_address,
            recipient=self.recipient,
        )

        last_error: BaseException | None = None
        for attempt in range(1, self._max_retry_attempts + 1):
            try:
                await self._smtp_sender(message, self._smtp_config)
                await self._circuit.record_success()
                logger.info(
                    "alert_send_success",
                    operation="send_alert",
                    username=user.username,
                    server=event_log.server,
                    score=user.score,
                    attempt=attempt,
                    circuit_state=self._circuit.state.value,
                )
                self._emit_audit_record(user, event_log, "alert_sent", "smtp_success")
                return
            except Exception as exc:
                last_error = exc
                transient = is_transient_smtp_error(exc)
                logger.warning(
                    "alert_send_failure",
                    operation="send_alert",
                    username=user.username,
                    server=event_log.server,
                    attempt=attempt,
                    transient=transient,
                    error=str(exc),
                    circuit_state=self._circuit.state.value,
                )
                if not transient or attempt >= self._max_retry_attempts:
                    break
                delay = self._retry_base_delay_seconds * (2 ** (attempt - 1))
                await asyncio.sleep(delay)

        await self._circuit.record_failure()
        reason = str(last_error) if last_error else "unknown_error"
        await self._dead_letter.write(
            self._dead_letter_payload(
                user,
                event_log,
                reason=reason,
            )
        )
        self._emit_audit_record(user, event_log, "alert_suppressed", reason)

    def send_email_alert(self, user: User, event_log: EventLog) -> None:
        """Sync adapter for the legacy scoring pipeline."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self.send_alert(user, event_log))
        else:
            loop.create_task(self.send_alert(user, event_log))

    @staticmethod
    def _dead_letter_payload(
        user: User,
        event_log: EventLog,
        *,
        reason: str,
    ) -> dict[str, Any]:
        return {
            "username": user.username,
            "server": event_log.server,
            "score": user.score,
            "timestamp": _format_alert_timestamp(event_log),
            "source_ip": event_log.ip_address,
            "reason": reason,
        }
