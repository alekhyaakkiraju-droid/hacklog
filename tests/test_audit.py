"""Tests for AuditRecord entity, AuditRepository, and audit integration."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

_TESTS_DIR = Path(__file__).resolve().parent
_HACKLOG_DIR = _TESTS_DIR.parent / "hacklog"
for _path in (_HACKLOG_DIR, _TESTS_DIR.parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from alerting import AlertService  # noqa: E402
from config import SmtpConfig  # noqa: E402
from entities import AuditRecord, EventLog, User, create_tables  # noqa: E402
from repositories import AuditRepository  # noqa: E402
from scoring import ScoringEngine  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def session_factory(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'audit_test.db'}")
    create_tables(engine)
    factory = sessionmaker(
        bind=engine, autoflush=True, autocommit=False, expire_on_commit=False
    )
    yield factory
    engine.dispose()


@pytest.fixture
def audit_repository(session_factory) -> AuditRepository:
    return AuditRepository(session_factory)


@pytest.fixture
def event_log() -> EventLog:
    return EventLog(
        datetime(2026, 3, 10, 14, 0, 0), "testuser", "10.0.0.5", False, "prod-host"
    )


@pytest.fixture
def user() -> User:
    return User("testuser", datetime(2026, 3, 10, 14, 0, 0), 0)


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


# ---------------------------------------------------------------------------
# AuditRecord entity tests
# ---------------------------------------------------------------------------


def test_audit_record_fields_stored_correctly(audit_repository, session_factory) -> None:
    ts = datetime(2026, 3, 10, 14, 0, 0, tzinfo=UTC)
    record = AuditRecord(
        timestamp=ts,
        actor="testuser",
        source_ip="10.0.0.5",
        resource="prod-host",
        action="score_calculated",
        outcome="42",
        details={"total_score": 42.0, "success_score": 35.0},
    )
    audit_repository.save_audit_record(record)

    with session_factory() as session:
        loaded = session.execute(select(AuditRecord)).scalars().first()

    assert loaded is not None
    assert loaded.actor == "testuser"
    assert loaded.source_ip == "10.0.0.5"
    assert loaded.resource == "prod-host"
    assert loaded.action == "score_calculated"
    assert loaded.outcome == "42"
    assert loaded.details["total_score"] == 42.0
    assert loaded.id is not None  # auto-increment primary key


def test_audit_record_id_autoincrement(audit_repository, session_factory) -> None:
    for i in range(3):
        record = AuditRecord(
            timestamp=datetime(2026, 3, 10, 14, i, 0),
            actor="user",
            source_ip="10.0.0.1",
            resource="server",
            action="score_calculated",
            outcome=str(i),
        )
        audit_repository.save_audit_record(record)

    with session_factory() as session:
        records = session.execute(select(AuditRecord)).scalars().all()

    assert len(records) == 3
    ids = [r.id for r in records]
    assert len(set(ids)) == 3  # all unique


# ---------------------------------------------------------------------------
# AuditRepository append-only tests
# ---------------------------------------------------------------------------


def test_audit_repository_has_no_update_method(audit_repository) -> None:
    """AuditRepository must not expose an update method — append-only."""
    assert not hasattr(audit_repository, "update_audit_record")
    assert not hasattr(audit_repository, "update")


def test_audit_repository_has_no_delete_method(audit_repository) -> None:
    """AuditRepository must not expose a delete method — append-only."""
    assert not hasattr(audit_repository, "delete_audit_record")
    assert not hasattr(audit_repository, "delete")


def test_audit_repository_save_audit_record_persists(
    audit_repository, session_factory
) -> None:
    record = AuditRecord(
        timestamp=datetime(2026, 3, 10, 15, 0, 0),
        actor="alice",
        source_ip="192.168.1.1",
        resource="app-server",
        action="alert_sent",
        outcome="alert_sent",
        details={"reason": "smtp_success", "score": 55},
    )
    audit_repository.save_audit_record(record)

    with session_factory() as session:
        rows = session.execute(select(AuditRecord)).scalars().all()

    assert len(rows) == 1
    assert rows[0].action == "alert_sent"


# ---------------------------------------------------------------------------
# ScoringEngine audit integration tests
# ---------------------------------------------------------------------------


def _make_mock_services(user: User):
    update_service = MagicMock()
    alert_service = MagicMock()
    update_service.fetch_user.return_value = user
    update_service.update_and_return_hour_freq_for_user.return_value = 0.5
    update_service.update_and_return_day_freq_for_user.return_value = 0.5
    update_service.update_and_return_server_freq_for_user.return_value = 0.5
    update_service.update_and_return_ip_freq_for_user.return_value = 0.5
    update_service.update_user_scare_count.side_effect = lambda u: u
    return update_service, alert_service


def test_scoring_engine_creates_audit_record_for_score_calculated(
    audit_repository, session_factory, event_log, user
) -> None:
    update_service, alert_service = _make_mock_services(user)
    engine = ScoringEngine(update_service, alert_service, audit_repository)
    engine.process_event_log(event_log)

    with session_factory() as session:
        records = session.execute(
            select(AuditRecord).where(AuditRecord.action == "score_calculated")
        ).scalars().all()

    assert len(records) >= 1
    rec = records[0]
    assert rec.actor == event_log.username
    assert rec.source_ip == event_log.ip_address
    assert rec.resource == event_log.server
    assert rec.outcome is not None
    assert rec.details is not None
    assert "total_score" in rec.details
    assert "alert_decision" in rec.details


def test_scoring_engine_audit_record_contains_all_dimension_scores(
    audit_repository, session_factory, event_log, user
) -> None:
    update_service, alert_service = _make_mock_services(user)
    engine = ScoringEngine(update_service, alert_service, audit_repository)
    engine.process_event_log(event_log)

    with session_factory() as session:
        rec = session.execute(
            select(AuditRecord).where(AuditRecord.action == "score_calculated")
        ).scalars().first()

    assert rec is not None
    for field in (
        "success_score",
        "ip_location_score",
        "server_score",
        "ip_score",
        "day_score",
        "hour_score",
        "total_score",
    ):
        assert field in rec.details, f"Missing dimension score: {field}"


def test_scoring_engine_scare_count_update_creates_audit_record(
    audit_repository, session_factory, event_log
) -> None:
    from entities import Threshold

    # User with scare_count=0 (below threshold), score will be > SCARY but < CRITICAL
    user = User("testuser", datetime(2026, 3, 10, 14, 0, 0), 0)
    user.scare_count = 0
    user.last_scare_date = datetime(2026, 3, 10, 14, 0, 0)

    update_service, alert_service = _make_mock_services(user)
    update_service.update_user_scare_count.side_effect = lambda u: u

    engine = ScoringEngine(update_service, alert_service, audit_repository)
    # Force a score that's SCARY but not CRITICAL
    engine.calculate_new_score = MagicMock(  # type: ignore[method-assign]
        return_value=(Threshold.SCARY + 1, {"total_score": float(Threshold.SCARY + 1)})
    )
    engine.process_event_log(event_log)

    with session_factory() as session:
        records = session.execute(
            select(AuditRecord).where(AuditRecord.action == "scare_count_updated")
        ).scalars().all()

    assert len(records) == 1


def test_scoring_engine_scare_count_reset_creates_audit_record(
    audit_repository, session_factory, event_log
) -> None:
    from entities import Threshold

    # User with old scare date so reset triggers
    user = User("testuser", datetime(2026, 1, 1, 0, 0, 0), 0)
    user.scare_count = 1
    user.last_scare_date = datetime(2026, 1, 1, 0, 0, 0)

    update_service, alert_service = _make_mock_services(user)
    # event_log date is 2026-03-10, last_scare_date is 2026-01-01 → > 1 day diff

    engine = ScoringEngine(update_service, alert_service, audit_repository)
    # Force a low score so reset path triggers
    engine.calculate_new_score = MagicMock(  # type: ignore[method-assign]
        return_value=(5, {"total_score": 5.0})
    )
    engine.process_event_log(event_log)

    with session_factory() as session:
        records = session.execute(
            select(AuditRecord).where(AuditRecord.action == "scare_count_reset")
        ).scalars().all()

    assert len(records) == 1


# ---------------------------------------------------------------------------
# AlertService audit integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alert_service_creates_audit_record_on_success(
    audit_repository, session_factory, smtp_config, event_log, user
) -> None:
    sender = AsyncMock()
    service = AlertService(
        smtp_config,
        smtp_sender=sender,
        audit_repository=audit_repository,
    )
    await service.send_alert(user, event_log)

    with session_factory() as session:
        records = session.execute(
            select(AuditRecord).where(AuditRecord.action == "alert_sent")
        ).scalars().all()

    assert len(records) == 1
    rec = records[0]
    assert rec.actor == user.username
    assert rec.resource == event_log.server
    assert rec.details is not None
    assert rec.details["reason"] == "smtp_success"


@pytest.mark.asyncio
async def test_alert_service_creates_audit_record_on_circuit_open(
    audit_repository, session_factory, smtp_config, event_log, user
) -> None:
    from alerting import CircuitBreaker

    breaker = CircuitBreaker(failure_threshold=1)
    await breaker.record_failure()
    service = AlertService(
        smtp_config,
        circuit_breaker=breaker,
        smtp_sender=AsyncMock(),
        audit_repository=audit_repository,
    )
    await service.send_alert(user, event_log)

    with session_factory() as session:
        records = session.execute(
            select(AuditRecord).where(AuditRecord.action == "alert_suppressed")
        ).scalars().all()

    assert len(records) == 1
    rec = records[0]
    assert rec.details["reason"] == "circuit_open"


@pytest.mark.asyncio
async def test_alert_service_creates_audit_record_on_smtp_failure(
    audit_repository, session_factory, smtp_config, event_log, user, tmp_path
) -> None:
    from aiosmtplib.errors import SMTPAuthenticationError

    dead_letter = tmp_path / "dl.jsonl"
    sender = AsyncMock(side_effect=SMTPAuthenticationError(535, "invalid credentials"))
    service = AlertService(
        smtp_config,
        smtp_sender=sender,
        dead_letter_path=dead_letter,
        audit_repository=audit_repository,
    )
    await service.send_alert(user, event_log)

    with session_factory() as session:
        records = session.execute(
            select(AuditRecord).where(AuditRecord.action == "alert_suppressed")
        ).scalars().all()

    assert len(records) == 1


# ---------------------------------------------------------------------------
# System integration test: full pipeline end-to-end
# ---------------------------------------------------------------------------


def test_full_pipeline_creates_audit_record_with_correct_fields(
    audit_repository, session_factory
) -> None:
    """Process an EventLog through the full scoring pipeline and verify audit record."""
    from entities import Threshold

    event = EventLog(
        datetime(2026, 4, 1, 9, 0, 0), "integration-user", "10.0.0.99", False, "int-host"
    )
    user = User("integration-user", datetime(2026, 4, 1, 9, 0, 0), 0)
    user.last_scare_date = datetime(2026, 4, 1, 9, 0, 0)

    update_service = MagicMock()
    alert_service = MagicMock()
    update_service.fetch_user.return_value = user
    update_service.update_and_return_hour_freq_for_user.return_value = 0.5
    update_service.update_and_return_day_freq_for_user.return_value = 0.5
    update_service.update_and_return_server_freq_for_user.return_value = 0.5
    update_service.update_and_return_ip_freq_for_user.return_value = 0.5
    update_service.update_user_scare_count.side_effect = lambda u: u

    engine = ScoringEngine(update_service, alert_service, audit_repository)
    engine.process_event_log(event)

    with session_factory() as session:
        records = session.execute(select(AuditRecord)).scalars().all()

    assert len(records) >= 1
    rec = next(r for r in records if r.action == "score_calculated")
    assert rec.actor == "integration-user"
    assert rec.source_ip == "10.0.0.99"
    assert rec.resource == "int-host"
    assert rec.outcome is not None
    assert rec.details is not None
    assert "total_score" in rec.details
    assert "alert_decision" in rec.details
    # UTC timestamp is set
    assert rec.timestamp is not None
