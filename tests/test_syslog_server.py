"""Tests for asyncio syslog_server module."""

from __future__ import annotations

import asyncio
import signal
import socket
from collections.abc import Callable
from unittest.mock import MagicMock

import pytest

from hacklog.entities import SyslogMsg
from hacklog.metrics import messages_dropped_total
from hacklog.security import IpAllowlist, MessageValidator, RateLimiter
from hacklog.syslog_server import SyslogProtocol, message_consumer, run_async_syslog_server


def _validator(
    *,
    cidrs: list[str] | None = None,
    max_size: int = 2048,
    rate: float = 100,
    burst: int = 100,
) -> MessageValidator:
    return MessageValidator(
        allowlist=IpAllowlist(cidrs or []),
        max_message_size=max_size,
        rate_limiter=RateLimiter(rate_per_second=rate, burst_capacity=burst),
        meter_and_log=False,
    )


@pytest.mark.asyncio
async def test_datagram_received_enqueues_valid_message() -> None:
    queue: asyncio.Queue = asyncio.Queue(maxsize=10)
    protocol = SyslogProtocol(queue, _validator(), accepting=lambda: True)
    protocol.datagram_received(b"hello syslog", ("127.0.0.1", 1234))

    msg = await queue.get()
    assert isinstance(msg, SyslogMsg)
    assert msg.data == "hello syslog"
    assert msg.host == "127.0.0.1"
    assert msg.port == 1234


@pytest.mark.asyncio
async def test_datagram_received_rejects_non_allowlisted_ip() -> None:
    queue: asyncio.Queue = asyncio.Queue(maxsize=10)
    protocol = SyslogProtocol(
        queue,
        _validator(cidrs=["10.0.0.0/8"]),
        accepting=lambda: True,
    )
    protocol.datagram_received(b"blocked", ("203.0.113.1", 9000))
    assert queue.empty()


@pytest.mark.asyncio
async def test_datagram_received_rejects_oversized_message() -> None:
    queue: asyncio.Queue = asyncio.Queue(maxsize=10)
    protocol = SyslogProtocol(queue, _validator(max_size=16), accepting=lambda: True)
    protocol.datagram_received(b"x" * 32, ("127.0.0.1", 9000))
    assert queue.empty()


@pytest.mark.asyncio
async def test_datagram_received_rate_limits_excessive_sources() -> None:
    queue: asyncio.Queue = asyncio.Queue(maxsize=10)
    protocol = SyslogProtocol(
        queue,
        _validator(rate=1, burst=1),
        accepting=lambda: True,
    )
    protocol.datagram_received(b"one", ("10.0.0.5", 9000))
    protocol.datagram_received(b"two", ("10.0.0.5", 9000))
    assert queue.qsize() == 1


@pytest.mark.asyncio
async def test_datagram_received_drops_when_queue_full() -> None:
    queue: asyncio.Queue = asyncio.Queue(maxsize=1)
    queue.put_nowait(SyslogMsg("existing", "127.0.0.1", 1))
    protocol = SyslogProtocol(queue, _validator(), accepting=lambda: True)

    before = messages_dropped_total.labels(reason="queue_full")._value.get()  # noqa: SLF001
    protocol.datagram_received(b"overflow", ("127.0.0.1", 9000))
    after = messages_dropped_total.labels(reason="queue_full")._value.get()  # noqa: SLF001
    assert after - before == 1.0
    assert queue.qsize() == 1


@pytest.mark.asyncio
async def test_message_consumer_processes_enqueued_messages() -> None:
    queue: asyncio.Queue = asyncio.Queue(maxsize=10)
    parser = MagicMock()
    parser.parseLogLine.return_value = object()
    processed: list[object] = []

    queue.put_nowait(SyslogMsg("payload", "127.0.0.1", 42))
    running = True

    async def consume_once() -> None:
        nonlocal running
        await message_consumer(
            queue,
            parser,
            processed.append,
            running=lambda: running,
        )

    task = asyncio.create_task(consume_once())
    await asyncio.sleep(0.1)
    running = False
    await task

    assert len(processed) == 1
    parser.parseLogLine.assert_called_once()


@pytest.mark.asyncio
async def test_udp_integration_receives_datagram_via_asyncio_server() -> None:
    queue: asyncio.Queue = asyncio.Queue(maxsize=10)
    loop = asyncio.get_running_loop()
    ready = asyncio.Event()

    class _TestProtocol(SyslogProtocol):
        def connection_made(self, transport: asyncio.BaseTransport) -> None:
            super().connection_made(transport)
            ready.set()

    transport, _protocol = await loop.create_datagram_endpoint(
        lambda: _TestProtocol(queue, _validator(cidrs=["127.0.0.0/8"]), accepting=lambda: True),
        local_addr=("127.0.0.1", 0),
    )
    await ready.wait()
    port = transport.get_extra_info("sockname")[1]

    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client.sendto(b"integration-test", ("127.0.0.1", port))
    client.close()

    msg = await asyncio.wait_for(queue.get(), timeout=2)
    transport.close()
    assert isinstance(msg, SyslogMsg)
    assert msg.data == "integration-test"


@pytest.mark.asyncio
async def test_run_async_syslog_server_graceful_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    loop = asyncio.get_running_loop()
    shutdown_callbacks: list[Callable[[], None]] = []

    def capture_signal_handler(sig: signal.Signals, callback: Callable[[], None]) -> None:
        shutdown_callbacks.append(callback)

    monkeypatch.setattr(loop, "add_signal_handler", capture_signal_handler)

    parser = MagicMock()
    parser.parseLogLine.return_value = None

    server_task = asyncio.create_task(
        run_async_syslog_server(
            bind_address="127.0.0.1",
            port=0,
            parser=parser,
            process_event=lambda _event: None,
            queue_maxsize=10,
            shutdown_drain_seconds=1,
        )
    )

    await asyncio.sleep(0.1)
    assert shutdown_callbacks
    shutdown_callbacks[0]()
    await asyncio.wait_for(server_task, timeout=5)


@pytest.mark.asyncio
async def test_end_to_end_udp_parse_and_process_wo002_corpus() -> None:
    """Send a WO-002 corpus syslog line over UDP and verify parse + process_event."""
    from entities import EventLog
    from parse import Parser

    wo002_line = (
        b"<14>sshd[3070]: Accepted publickey for kantselovich from 10.42.10.2 port 2005 ssh2"
    )
    parser = Parser()
    processed: list[object] = []
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    running = True

    consumer_task = asyncio.create_task(
        message_consumer(
            queue,
            parser,
            processed.append,
            running=lambda: running,
        )
    )

    ready = asyncio.Event()

    class _Listener(SyslogProtocol):
        def connection_made(self, transport: asyncio.BaseTransport) -> None:
            super().connection_made(transport)
            ready.set()

    transport, _protocol = await loop.create_datagram_endpoint(
        lambda: _Listener(queue, _validator(), accepting=lambda: True),
        local_addr=("127.0.0.1", 0),
    )
    await ready.wait()
    port = transport.get_extra_info("sockname")[1]

    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client.sendto(wo002_line, ("127.0.0.1", port))
    client.close()

    await asyncio.sleep(0.2)
    running = False
    transport.close()
    await asyncio.wait_for(consumer_task, timeout=2)

    assert len(processed) == 1
    assert isinstance(processed[0], EventLog)
