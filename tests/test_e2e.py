"""End-to-end integration tests for the full hacklog pipeline (WO-029)."""

from __future__ import annotations

import asyncio
import json
import socket
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select

_TESTS_DIR = Path(__file__).resolve().parent
_HACKLOG_DIR = _TESTS_DIR.parent / "hacklog"
for _path in (_HACKLOG_DIR, _TESTS_DIR.parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from hacklog.alerting import AlertService  # noqa: E402
from hacklog.config import SmtpConfig, SyslogConfig  # noqa: E402
from hacklog.entities import (  # noqa: E402
    Days,
    EventLog,
    Hours,
    IpAddress,
    Server,
    SyslogMsg,
    Threshold,
    User,
    Weight,
    create_tables,
)
from hacklog.parse import Parser  # noqa: E402
from hacklog.scoring import ScoringEngine  # noqa: E402
from hacklog.services import UpdateService, HourRangeEnum  # noqa: E402
from hacklog.syslog_server import SyslogProtocol, build_validator, message_consumer  # noqa: E402

TOLERANCE = 1e-9

LINUX_FAILURE_SYSLOG = (
    b"<14>sshd[4105]: pam_unix(sshd:auth): authentication failure; login= "
    b"uid=0 euid=0 tty=ssh ruser= rhost=203.0.113.50 user=e2euser"
)

LINUX_SUCCESS_SYSLOG = (
    b"<14>sshd[3070]: Accepted publickey for e2euser from 10.42.10.2 port 2005 ssh2"
)


class E2EPipeline:
    """Wire UDP ingestion, parsing, scoring, SQLite persistence, and alerting."""

    def __init__(
        self,
        *,
        session_factory,
        scoring_engine: ScoringEngine,
        syslog_config: SyslogConfig,
    ) -> None:
        self.session_factory = session_factory
        self.scoring_engine = scoring_engine
        self.syslog_config = syslog_config
        self.parser = Parser()
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self.running = True
        self.transport = None
        self.consumer_task: asyncio.Task | None = None
        self.port: int = 0

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        ready = asyncio.Event()
        validator = build_validator(self.syslog_config)

        class _Listener(SyslogProtocol):
            def connection_made(self, transport: asyncio.BaseTransport) -> None:
                super().connection_made(transport)
                ready.set()

        self.transport, _protocol = await loop.create_datagram_endpoint(
            lambda: _Listener(
                self.queue,
                validator,
                accepting=lambda: self.running,
            ),
            local_addr=(self.syslog_config.bind_address, 0),
        )
        await ready.wait()
        self.port = self.transport.get_extra_info("sockname")[1]
        self.consumer_task = asyncio.create_task(
            message_consumer(
                self.queue,
                self.parser,
                self.scoring_engine.process_event_log,
                running=lambda: self.running,
            )
        )

    async def stop(self) -> None:
        self.running = False
        await asyncio.sleep(0.15)
        if self.transport is not None:
            self.transport.close()
        if self.consumer_task is not None:
            await asyncio.wait_for(self.consumer_task, timeout=3)

    def send_udp(self, payload: bytes, source_host: str = "127.0.0.1") -> None:
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.sendto(payload, (self.syslog_config.bind_address, self.port))
        client.close()

    def event_log_count(self) -> int:
        with self.session_factory() as session:
            return session.execute(
                select(func.count()).select_from(EventLog)
            ).scalar_one()

    def get_user(self, username: str) -> User | None:
        with self.session_factory() as session:
            return session.execute(
                select(User).where(User.username == username)
            ).scalar_one_or_none()


@pytest.fixture
async def e2e_pipeline(e2e_services, e2e_syslog_config):
    scoring_engine, _update, _alert, _smtp = e2e_services
    pipeline = E2EPipeline(
        session_factory=scoring_engine._update_service._user_repository.session_factory,
        scoring_engine=scoring_engine,
        syslog_config=e2e_syslog_config,
    )
    await pipeline.start()
    yield pipeline
    await pipeline.stop()


def _parse_golden_event(raw: dict) -> EventLog:
    data = raw["input"]
    return EventLog(
        datetime.strptime(data["date"], "%Y-%m-%dT%H:%M:%S"),
        data["username"],
        data["ipAddress"],
        data["success"],
        data["server"],
    )


def _assert_close(actual: float, expected: float) -> None:
    assert abs(actual - expected) <= TOLERANCE, f"expected {expected}, got {actual}"


@pytest.mark.asyncio
async def test_e2e_udp_parse_score_persist(e2e_pipeline: E2EPipeline) -> None:
    e2e_pipeline.send_udp(LINUX_FAILURE_SYSLOG)
    await asyncio.sleep(0.25)
    assert e2e_pipeline.event_log_count() == 1
    user = e2e_pipeline.get_user("e2euser")
    assert user is not None
    assert user.score > 0


@pytest.mark.asyncio
async def test_e2e_critical_score_triggers_alert(
    e2e_pipeline: E2EPipeline,
    mock_smtp_sender,
) -> None:
    """Failure plus rare behavioral profiles pushes score above CRITICAL."""
    update_service = e2e_pipeline.scoring_engine._update_service
    username = "alertuser"
    now = datetime.now()
    hour = now.hour
    range_name = "morning"
    for hour_range, name in zip(
        [
            HourRangeEnum.EARLY,
            HourRangeEnum.DAWN,
            HourRangeEnum.MORNING,
            HourRangeEnum.AFTERNOON,
            HourRangeEnum.EVE,
            HourRangeEnum.NIGHT,
        ],
        ["early", "dawn", "morning", "afternoon", "eve", "night"],
        strict=False,
    ):
        if hour in hour_range:
            range_name = name
            break

    rare = 1
    total = 500
    update_service._profile_repository.save_profile(
        Hours(now, username, {range_name: rare}, total)
    )
    update_service._profile_repository.save_profile(
        Days(now, username, {now.strftime("%a"): rare}, total)
    )
    update_service._profile_repository.save_profile(
        Server(now, username, {"127.0.0.1": rare}, total)
    )
    update_service._profile_repository.save_profile(
        IpAddress(now, username, {"203.0.113.50": rare}, total)
    )

    e2e_pipeline.send_udp(
        LINUX_FAILURE_SYSLOG.replace(b"e2euser", b"alertuser"),
    )
    await asyncio.sleep(0.25)
    mock_smtp_sender.assert_awaited()


@pytest.mark.asyncio
async def test_e2e_normal_score_does_not_alert(
    e2e_pipeline: E2EPipeline,
    mock_smtp_sender,
) -> None:
    e2e_pipeline.send_udp(LINUX_SUCCESS_SYSLOG)
    await asyncio.sleep(0.25)
    mock_smtp_sender.assert_not_awaited()
    user = e2e_pipeline.get_user("e2euser")
    assert user is not None
    assert user.score <= Threshold.SCARY


@pytest.mark.asyncio
async def test_e2e_scare_counter_escalation_triggers_alert(
    sqlite_session_factory,
    smtp_config,
    mock_smtp_sender,
) -> None:
    update_service = UpdateService(session_factory=sqlite_session_factory)
    alert_service = AlertService(smtp_config, smtp_sender=mock_smtp_sender)
    engine = ScoringEngine(update_service, alert_service)

    scary_score = Threshold.SCARY + 5
    user = User("scareuser", datetime(2026, 1, 15, 10, 0, 0), 0)
    user.scare_count = 0
    update_service._user_repository.save(user)

    event = EventLog(
        datetime(2026, 1, 15, 10, 0, 0),
        "scareuser",
        "203.0.113.9",
        False,
        "prod-host",
    )

    engine.calculate_new_score = MagicMock(  # type: ignore[method-assign]
        return_value=(scary_score, {"total_score": float(scary_score)})
    )

    for _ in range(Threshold.SCARECOUNT):
        engine.process_event_log(event)
        await asyncio.sleep(0)

    engine.process_event_log(event)
    await asyncio.sleep(0.05)
    mock_smtp_sender.assert_awaited()


@pytest.mark.asyncio
async def test_e2e_ip_allowlist_rejects_non_allowlisted_source(
    e2e_services,
    mock_smtp_sender,
) -> None:
    scoring_engine, _, _, _ = e2e_services
    config = SyslogConfig(
        bind_address="127.0.0.1",
        allowed_cidrs=["10.0.0.0/8"],
        rate_limit_per_source=100,
    )
    pipeline = E2EPipeline(
        session_factory=scoring_engine._update_service._user_repository.session_factory,
        scoring_engine=scoring_engine,
        syslog_config=config,
    )
    await pipeline.start()
    try:
        pipeline.send_udp(LINUX_FAILURE_SYSLOG)
        await asyncio.sleep(0.2)
        assert pipeline.event_log_count() == 0
    finally:
        await pipeline.stop()


@pytest.mark.asyncio
async def test_e2e_rate_limiting_drops_excess_messages(e2e_services) -> None:
    scoring_engine, _, _, _ = e2e_services
    config = SyslogConfig(
        bind_address="127.0.0.1",
        allowed_cidrs=[],
        rate_limit_per_source=1,
    )
    pipeline = E2EPipeline(
        session_factory=scoring_engine._update_service._user_repository.session_factory,
        scoring_engine=scoring_engine,
        syslog_config=config,
    )
    await pipeline.start()
    try:
        pipeline.send_udp(LINUX_FAILURE_SYSLOG)
        pipeline.send_udp(LINUX_FAILURE_SYSLOG)
        await asyncio.sleep(0.25)
        assert pipeline.event_log_count() == 1
    finally:
        await pipeline.stop()


def test_e2e_golden_corpus_scoring_parity(scoring_golden_events) -> None:
    """All 527 WO-001 golden events match ScoringEngine.calculate_new_score."""
    update_service = MagicMock(spec=UpdateService)
    alert_service = MagicMock()
    engine = ScoringEngine(update_service, alert_service)

    for raw in scoring_golden_events:
        event = _parse_golden_event(raw)
        freqs = raw["frequencies"]
        expected = raw["expected"]
        update_service.update_and_return_hour_freq_for_user.return_value = freqs["hour"]
        update_service.update_and_return_day_freq_for_user.return_value = freqs["day"]
        update_service.update_and_return_server_freq_for_user.return_value = freqs["server"]
        update_service.update_and_return_ip_freq_for_user.return_value = freqs["ip"]

        success = engine.calculate_success_score(event.success)
        ip_loc = engine.calculate_ip_location_score(event.ip_address)
        hour = engine.calculate_subscore(freqs["hour"]) * Weight.HOURS
        day = engine.calculate_subscore(freqs["day"]) * Weight.DAYS
        server = engine.calculate_subscore(freqs["server"]) * Weight.SERVER
        ip = engine.calculate_subscore(freqs["ip"]) * Weight.IP

        _assert_close(success, expected["success"])
        _assert_close(ip_loc, expected["ip_location"])
        _assert_close(hour, expected["hours"])
        _assert_close(day, expected["days"])
        _assert_close(server, expected["server"])
        _assert_close(ip, expected["ip"])

        total, dims = engine.calculate_new_score(event)
        _assert_close(dims["total_score"], expected["total"])


@pytest.mark.asyncio
async def test_e2e_syslog_corpus_over_udp(e2e_pipeline: E2EPipeline) -> None:
    """WO-002 syslog corpus messages parse and persist through the live UDP path."""
    corpus_path = _TESTS_DIR / "fixtures" / "syslog_corpus.json"
    with corpus_path.open(encoding="utf-8") as handle:
        corpus = json.load(handle)

    processed_before = e2e_pipeline.event_log_count()
    sent = 0
    for entry in corpus["messages"][:10]:
        raw = entry.get("raw") or entry.get("message")
        if not raw:
            continue
        payload = raw.encode("utf-8") if isinstance(raw, str) else raw
        e2e_pipeline.send_udp(payload)
        sent += 1

    await asyncio.sleep(0.5)
    assert sent > 0
    assert e2e_pipeline.event_log_count() > processed_before
