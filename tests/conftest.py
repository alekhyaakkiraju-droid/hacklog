"""Shared pytest fixtures for behavioral and end-to-end pipeline tests."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_TESTS_DIR = Path(__file__).resolve().parent
_HACKLOG_DIR = _TESTS_DIR.parent / "hacklog"
for _path in (_HACKLOG_DIR, _TESTS_DIR.parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from hacklog.alerting import AlertService  # noqa: E402
from hacklog.config import SmtpConfig, SyslogConfig  # noqa: E402
from hacklog.entities import EventLog, User, create_tables  # noqa: E402
from hacklog.scoring import ScoringEngine  # noqa: E402
from hacklog.services import UpdateService  # noqa: E402


@pytest.fixture
def sample_event_log() -> EventLog:
    return EventLog(
        datetime(2026, 1, 15, 10, 0, 0),
        "nrhine",
        "10.42.10.2",
        False,
        "prod-host",
    )


@pytest.fixture
def mock_scoring_services():
    update_service = MagicMock(spec=UpdateService)
    alert_service = MagicMock()
    user = User("nrhine", datetime(2026, 1, 15, 10, 0, 0), 0)
    user.scare_count = 0
    update_service.fetch_user.return_value = user
    update_service.update_and_return_hour_freq_for_user.return_value = 0.5
    update_service.update_and_return_day_freq_for_user.return_value = 0.5
    update_service.update_and_return_server_freq_for_user.return_value = 0.5
    update_service.update_and_return_ip_freq_for_user.return_value = 0.5
    update_service.update_user_scare_count.return_value = user
    engine = ScoringEngine(update_service, alert_service)
    return engine, update_service, alert_service, user


@pytest.fixture
def sqlite_session_factory():
    engine = create_engine("sqlite:///:memory:")
    create_tables(engine)
    factory = sessionmaker(
        bind=engine, autoflush=True, autocommit=False, expire_on_commit=False
    )
    yield factory


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
def mock_smtp_sender() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def e2e_syslog_config() -> SyslogConfig:
    return SyslogConfig(
        bind_address="127.0.0.1",
        max_message_size=2048,
        allowed_cidrs=[],
        rate_limit_per_source=100,
    )


@pytest.fixture
def e2e_services(sqlite_session_factory, smtp_config, mock_smtp_sender):
    """Real UpdateService + ScoringEngine with in-memory SQLite and mock SMTP."""
    update_service = UpdateService(session_factory=sqlite_session_factory)
    alert_service = AlertService(
        smtp_config,
        smtp_sender=mock_smtp_sender,
    )
    scoring_engine = ScoringEngine(update_service, alert_service)
    return scoring_engine, update_service, alert_service, mock_smtp_sender


@pytest.fixture
def scoring_golden_events():
    import json

    path = _TESTS_DIR / "fixtures" / "scoring_golden.json"
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    events = payload["events"]
    assert len(events) >= 500
    return events
