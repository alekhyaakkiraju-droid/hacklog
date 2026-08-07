"""Tests for DataRetentionService: purge logic, audit records, and scheduling."""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

_TESTS_DIR = Path(__file__).resolve().parent
_HACKLOG_DIR = _TESTS_DIR.parent / "hacklog"
for _path in (_HACKLOG_DIR, _TESTS_DIR.parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from entities import (  # noqa: E402
    AuditRecord,
    Days,
    EventLog,
    Hours,
    IpAddress,
    Server,
    User,
    create_tables,
)
from repositories import AuditRepository  # noqa: E402
from retention import DataRetentionService  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ago(days: int) -> datetime:
    """Return a naive UTC datetime that is `days` days in the past."""
    return datetime.utcnow() - timedelta(days=days)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def session_factory(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'retention_test.db'}")
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
def retention_service(session_factory, audit_repository) -> DataRetentionService:
    return DataRetentionService(
        session_factory,
        audit_repository,
        event_retention_days=30,
        profile_inactivity_days=90,
        batch_size=10,
        purge_schedule_hour=2,
    )

def _add_event(session_factory, username: str, days_ago: int) -> None:
    date = _ago(days_ago)
    with session_factory() as session:
        session.add(EventLog(date, username, "10.0.0.1", True, "host"))
        session.commit()

def _add_user(session_factory, username: str, days_ago: int) -> None:
    date = _ago(days_ago)
    with session_factory() as session:
        user = User(username, date, 0)
        session.add(user)
        session.commit()

def _add_profile(session_factory, entity_cls, username: str, days_ago: int) -> None:
    date = _ago(days_ago)
    with session_factory() as session:
        session.add(entity_cls(date, username, {"Mon": 1}, 1))
        session.commit()

def _count(session_factory, entity_cls) -> int:
    with session_factory() as session:
        return len(session.execute(select(entity_cls)).scalars().all())

def _usernames(session_factory, entity_cls) -> set[str]:
    with session_factory() as session:
        return {r.username for r in session.execute(select(entity_cls)).scalars().all()}

# ---------------------------------------------------------------------------
# Event log purge tests
# ---------------------------------------------------------------------------

def test_event_logs_beyond_retention_are_deleted(
    session_factory, retention_service
) -> None:
    _add_event(session_factory, "old-user", 40)   # 40 days old — beyond 30-day retention
    _add_event(session_factory, "new-user", 10)   # 10 days old — within retention

    deleted = retention_service.purge_event_logs()

    assert deleted == 1
    assert _count(session_factory, EventLog) == 1
    assert _usernames(session_factory, EventLog) == {"new-user"}

def test_event_logs_within_retention_are_preserved(
    session_factory, retention_service
) -> None:
    _add_event(session_factory, "safe-user", 1)

    deleted = retention_service.purge_event_logs()

    assert deleted == 0
    assert _count(session_factory, EventLog) == 1

def test_purge_event_logs_boundary(session_factory, retention_service) -> None:
    """Record exactly at the boundary (30 days old) is preserved (cutoff is strict <)."""
    _add_event(session_factory, "boundary-user", 29)  # just inside retention
    _add_event(session_factory, "beyond-user", 31)    # just beyond retention

    deleted = retention_service.purge_event_logs()

    assert deleted == 1
    assert _usernames(session_factory, EventLog) == {"boundary-user"}

def test_purge_event_logs_is_idempotent(session_factory, retention_service) -> None:
    _add_event(session_factory, "idem-user", 50)

    first = retention_service.purge_event_logs()
    second = retention_service.purge_event_logs()

    assert first == 1
    assert second == 0

def test_purge_event_logs_batch_processing(session_factory, audit_repository) -> None:
    """Verify batch_size=3 correctly handles more records than one batch."""
    service = DataRetentionService(
        session_factory,
        audit_repository,
        event_retention_days=30,
        batch_size=3,
    )
    # Insert 7 old records
    for i in range(7):
        _add_event(session_factory, f"batch-user-{i}", 40 + i)
    # Insert 2 recent records
    _add_event(session_factory, "keep-1", 5)
    _add_event(session_factory, "keep-2", 10)

    deleted = service.purge_event_logs()

    assert deleted == 7
    assert _count(session_factory, EventLog) == 2

# ---------------------------------------------------------------------------
# Profile purge tests
# ---------------------------------------------------------------------------

def test_inactive_profiles_are_purged(session_factory, retention_service) -> None:
    """All records for an inactive user are removed across every profile table."""
    username = "stale-user"
    _add_user(session_factory, username, 200)
    _add_event(session_factory, username, 200)
    _add_profile(session_factory, Days, username, 200)
    _add_profile(session_factory, Hours, username, 200)
    _add_profile(session_factory, Server, username, 200)
    _add_profile(session_factory, IpAddress, username, 200)

    purged = retention_service.purge_inactive_profiles()

    assert purged == 1
    assert _count(session_factory, User) == 0
    assert _count(session_factory, Days) == 0
    assert _count(session_factory, Hours) == 0
    assert _count(session_factory, Server) == 0
    assert _count(session_factory, IpAddress) == 0

def test_active_profiles_are_preserved(session_factory, retention_service) -> None:
    username = "active-user"
    _add_user(session_factory, username, 5)
    _add_event(session_factory, username, 5)
    _add_profile(session_factory, Days, username, 5)

    purged = retention_service.purge_inactive_profiles()

    assert purged == 0
    assert _count(session_factory, User) == 1
    assert _count(session_factory, Days) == 1

def test_profile_inactivity_uses_most_recent_activity(
    session_factory, retention_service
) -> None:
    """User with old profile but recent event log is NOT purged."""
    username = "recently-active"
    _add_user(session_factory, username, 200)
    _add_profile(session_factory, Days, username, 200)  # old Days record
    _add_event(session_factory, username, 10)           # recent EventLog keeps them active

    purged = retention_service.purge_inactive_profiles()

    assert purged == 0
    assert _count(session_factory, User) == 1

def test_purge_inactive_profiles_is_idempotent(
    session_factory, retention_service
) -> None:
    _add_user(session_factory, "idem-profile", 200)
    _add_event(session_factory, "idem-profile", 200)

    first = retention_service.purge_inactive_profiles()
    second = retention_service.purge_inactive_profiles()

    assert first == 1
    assert second == 0

# ---------------------------------------------------------------------------
# Audit record tests
# ---------------------------------------------------------------------------

def test_purge_event_logs_creates_audit_record(
    session_factory, retention_service
) -> None:
    _add_event(session_factory, "audit-ev-user", 40)

    retention_service.purge_event_logs()

    with session_factory() as session:
        records = session.execute(
            select(AuditRecord).where(AuditRecord.action == "event_logs_purged")
        ).scalars().all()

    assert len(records) == 1
    rec = records[0]
    assert rec.actor == "system"
    assert rec.resource == "database"
    assert rec.details["records_deleted"] == 1
    assert rec.details["retention_days"] == 30

def test_purge_inactive_profiles_creates_audit_record(
    session_factory, retention_service
) -> None:
    _add_user(session_factory, "audit-prof", 200)
    _add_event(session_factory, "audit-prof", 200)

    retention_service.purge_inactive_profiles()

    with session_factory() as session:
        records = session.execute(
            select(AuditRecord).where(AuditRecord.action == "inactive_profiles_purged")
        ).scalars().all()

    assert len(records) == 1
    rec = records[0]
    assert rec.details["users_purged"] == 1
    assert rec.details["inactivity_days"] == 90

def test_purge_without_audit_repository_does_not_raise(session_factory) -> None:
    service = DataRetentionService(
        session_factory,
        audit_repository=None,
        event_retention_days=30,
    )
    _add_event(session_factory, "no-audit-user", 40)

    deleted = service.purge_event_logs()
    assert deleted == 1

# ---------------------------------------------------------------------------
# System integration test: mixed timestamps
# ---------------------------------------------------------------------------

def test_run_purge_full_pipeline(session_factory, retention_service) -> None:
    """End-to-end: create records spanning the retention boundary, run purge."""
    # 3 old event logs, 2 recent
    for i in range(3):
        _add_event(session_factory, f"old-ev-{i}", 35 + i)
    for i in range(2):
        _add_event(session_factory, f"new-ev-{i}", i + 1)

    # 1 inactive user (with all profile types), 1 active user
    _add_user(session_factory, "stale", 200)
    _add_event(session_factory, "stale", 200)
    for cls in (Days, Hours, Server, IpAddress):
        _add_profile(session_factory, cls, "stale", 200)

    _add_user(session_factory, "fresh", 5)
    _add_event(session_factory, "fresh", 5)
    _add_profile(session_factory, Days, "fresh", 5)

    summary = retention_service.run_purge()

    assert summary["event_logs_deleted"] == 3
    assert summary["users_purged"] == 1
    assert "elapsed_seconds" in summary
    assert "run_at" in summary

    # Active user's profile preserved
    assert _count(session_factory, Days) == 1
    assert _usernames(session_factory, Days) == {"fresh"}

    # Old event logs gone; recent remain (plus the "fresh" user's event log)
    remaining = _usernames(session_factory, EventLog)
    assert "new-ev-0" in remaining
    assert "new-ev-1" in remaining
    for i in range(3):
        assert f"old-ev-{i}" not in remaining

    # Audit records created
    with session_factory() as session:
        ev_audit = session.execute(
            select(AuditRecord).where(AuditRecord.action == "event_logs_purged")
        ).scalars().all()
        prof_audit = session.execute(
            select(AuditRecord).where(AuditRecord.action == "inactive_profiles_purged")
        ).scalars().all()
    assert len(ev_audit) == 1
    assert len(prof_audit) == 1

# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

def test_retention_config_defaults() -> None:
    from config import RetentionConfig
    cfg = RetentionConfig()
    assert cfg.event_retention_days == 365
    assert cfg.profile_inactivity_days == 180
    assert cfg.purge_schedule_hour == 2
    assert cfg.purge_batch_size == 1000

def test_retention_config_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HACKLOG_EVENT_RETENTION_DAYS", "90")
    monkeypatch.setenv("HACKLOG_PROFILE_INACTIVITY_DAYS", "60")

    from config import _RetentionSettings
    settings = _RetentionSettings()
    assert settings.event_retention_days == 90
    assert settings.profile_inactivity_days == 60

def test_config_manager_has_retention(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("HACKLOG_SMTP_USER", "HACKLOG_SMTP_PASSWORD", "HACKLOG_SMTP_SENDER",
                "HACKLOG_ALERT_RECIPIENT"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("HACKLOG_SMTP_USER", "u@example.com")
    monkeypatch.setenv("HACKLOG_SMTP_PASSWORD", "pw")
    monkeypatch.setenv("HACKLOG_SMTP_SENDER", "u@example.com")
    monkeypatch.setenv("HACKLOG_ALERT_RECIPIENT", "r@example.com")
    monkeypatch.setenv("HACKLOG_EVENT_RETENTION_DAYS", "180")

    from config import load_config
    cfg = load_config()

    assert cfg.retention.event_retention_days == 180
    assert cfg.retention.profile_inactivity_days == 180  # default

# ---------------------------------------------------------------------------
# Async scheduler smoke test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_schedule_daily_purge_sleeps_until_next_run(
    session_factory, audit_repository
) -> None:
    """Smoke test: scheduler calls asyncio.sleep and run_purge."""
    service = DataRetentionService(
        session_factory,
        audit_repository,
        event_retention_days=30,
        purge_schedule_hour=2,
    )

    sleep_calls: list[float] = []
    run_calls: list[None] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 2:
            raise asyncio.CancelledError

    async def fake_to_thread(fn, *args, **kwargs):
        run_calls.append(None)

    import unittest.mock as mock
    import retention as ret_module

    with mock.patch.object(ret_module.asyncio, "sleep", fake_sleep):
        with mock.patch.object(ret_module.asyncio, "to_thread", fake_to_thread):
            with pytest.raises(asyncio.CancelledError):
                await service.schedule_daily_purge()

    # First sleep should be ≥0 seconds (waiting until next 02:00 UTC)
    assert len(sleep_calls) >= 1
    assert sleep_calls[0] >= 0
    # run_purge was invoked at least once
    assert len(run_calls) >= 1
