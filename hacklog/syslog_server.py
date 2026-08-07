"""Asyncio UDP syslog listener and message consumer."""

from __future__ import annotations

import asyncio
import os
import signal
from collections.abc import Callable
from typing import TYPE_CHECKING

try:
    from hacklog.config import SyslogConfig
    from hacklog.entities import SyslogMsg
    from hacklog.logging_config import get_logger
    from hacklog.metrics import messages_dropped_total, queue_depth
    from hacklog.security import MessageValidator, build_message_validator
except ImportError:
    from config import SyslogConfig
    from entities import SyslogMsg
    from logging_config import get_logger
    from metrics import messages_dropped_total, queue_depth
    from security import MessageValidator, build_message_validator

if TYPE_CHECKING:
    from parse import Parser

logger = get_logger("syslog_server")

DEFAULT_QUEUE_MAXSIZE = 10_000
DEFAULT_SHUTDOWN_DRAIN_SECONDS = 30.0
DEFAULT_PAYLOAD_ENCODING = "utf-8"
_POISON_PILL = object()


def syslog_payload_encoding() -> str:
    """Return configured syslog payload text encoding (default UTF-8)."""
    return os.environ.get("HACKLOG_SYSLOG_ENCODING", DEFAULT_PAYLOAD_ENCODING)


def build_validator(syslog_config: SyslogConfig | None = None) -> MessageValidator:
    """Build a MessageValidator from syslog configuration."""
    if syslog_config is None:
        return build_message_validator()
    return build_message_validator(
        allowed_cidrs=syslog_config.allowed_cidrs,
        max_message_size=syslog_config.max_message_size,
        rate_per_second=float(syslog_config.rate_limit_per_source),
        burst_capacity=syslog_config.rate_limit_per_source,
    )


class SyslogProtocol(asyncio.DatagramProtocol):
    """Asyncio datagram protocol for syslog UDP ingestion."""

    def __init__(
        self,
        queue: asyncio.Queue[SyslogMsg | object],
        validator: MessageValidator,
        *,
        encoding: str = DEFAULT_PAYLOAD_ENCODING,
        accepting: Callable[[], bool],
    ) -> None:
        self._queue = queue
        self._validator = validator
        self._encoding = encoding
        self._accepting = accepting
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]
        logger.debug(
            "udp_listener_started",
            operation="connection_made",
        )

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if not self._accepting():
            return

        host, port = addr
        validation = self._validator.validate(host, data)
        if not validation.accepted:
            return

        try:
            text = data.decode(self._encoding, errors="replace")
        except LookupError:
            text = data.decode(DEFAULT_PAYLOAD_ENCODING, errors="replace")

        syslog_msg = SyslogMsg(text, host, port)
        try:
            self._queue.put_nowait(syslog_msg)
            queue_depth.set(self._queue.qsize())
        except asyncio.QueueFull:
            messages_dropped_total.labels(reason="queue_full").inc()
            logger.warning(
                "message_dropped",
                operation="enqueue_datagram",
                source_ip=host,
                reason="queue_full",
                message_size=len(data),
            )

    def connection_lost(self, exc: Exception | None) -> None:
        logger.debug(
            "udp_listener_stopped",
            operation="connection_lost",
            error=str(exc) if exc else None,
        )


async def message_consumer(
    queue: asyncio.Queue[SyslogMsg | object],
    parser: Parser,
    process_event: Callable[[object], None],
    *,
    running: Callable[[], bool],
) -> None:
    """Drain the syslog queue and process parsed events."""
    while running() or not queue.empty():
        try:
            msg = await asyncio.wait_for(queue.get(), timeout=0.25)
        except TimeoutError:
            continue

        if msg is _POISON_PILL:
            queue.task_done()
            break

        if not isinstance(msg, SyslogMsg):
            queue.task_done()
            continue

        try:
            queue_depth.set(queue.qsize())
            event_log = parser.parseLogLine(msg)
            if event_log:
                process_event(event_log)
                logger.debug(
                    "message_processed",
                    operation="process_message",
                    queue_size=queue.qsize(),
                    source_host=msg.host,
                    source_port=msg.port,
                )
        finally:
            queue.task_done()


async def run_async_syslog_server(
    *,
    bind_address: str,
    port: int,
    parser: Parser,
    process_event: Callable[[object], None],
    syslog_config: SyslogConfig | None = None,
    queue_maxsize: int = DEFAULT_QUEUE_MAXSIZE,
    shutdown_drain_seconds: float = DEFAULT_SHUTDOWN_DRAIN_SECONDS,
    encoding: str | None = None,
) -> None:
    """Run the asyncio syslog UDP server until SIGINT or SIGTERM."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[SyslogMsg | object] = asyncio.Queue(maxsize=queue_maxsize)
    validator = build_validator(syslog_config)
    accepting = True
    running = True
    shutdown_requested = asyncio.Event()

    def stop_accepting() -> None:
        nonlocal accepting
        accepting = False

    def is_accepting() -> bool:
        return accepting

    def is_running() -> bool:
        return running

    def request_shutdown() -> None:
        logger.info("shutdown_requested", operation="handle_signal")
        stop_accepting()
        shutdown_requested.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, request_shutdown)

    transport, _protocol = await loop.create_datagram_endpoint(
        lambda: SyslogProtocol(
            queue,
            validator,
            encoding=encoding or syslog_payload_encoding(),
            accepting=is_accepting,
        ),
        local_addr=(bind_address, port),
    )

    consumer_task = asyncio.create_task(
        message_consumer(queue, parser, process_event, running=is_running)
    )

    logger.info(
        "syslog_server_listening",
        operation="start_listener",
        bind_address=bind_address,
        port=port,
        queue_maxsize=queue_maxsize,
    )

    await shutdown_requested.wait()
    running = False

    try:
        await asyncio.wait_for(queue.join(), timeout=shutdown_drain_seconds)
    except TimeoutError:
        logger.warning(
            "shutdown_queue_drain_timeout",
            operation="drain_queue",
            timeout_seconds=shutdown_drain_seconds,
            remaining=queue.qsize(),
        )

    try:
        queue.put_nowait(_POISON_PILL)
    except asyncio.QueueFull:
        await queue.put(_POISON_PILL)

    await consumer_task
    transport.close()
