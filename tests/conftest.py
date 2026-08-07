"""Shared pytest fixtures for scoring and service behavioral tests."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_TESTS_DIR = Path(__file__).resolve().parent
_HACKLOG_DIR = _TESTS_DIR.parent / "hacklog"
for _path in (_HACKLOG_DIR, _TESTS_DIR.parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from entities import EventLog, Threshold, User, create_tables  # noqa: E402
from repositories import AuditRepository, ProfileRepository, UserRepository  # noqa: E402
from scoring import ScoringEngine  # noqa: E402
from services import UpdateService  # noqa: E402


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
def sqlite_session_factory(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'scoring.db'}")
    create_tables(engine)
    factory = sessionmaker(
        bind=engine, autoflush=True, autocommit=False, expire_on_commit=False
    )
    yield factory
    engine.dispose()


@pytest.fixture
def update_service(sqlite_session_factory) -> UpdateService:
    return UpdateService(
        session_factory=sqlite_session_factory,
        profile_repository=ProfileRepository(sqlite_session_factory),
        user_repository=UserRepository(sqlite_session_factory),
        audit_repository=AuditRepository(sqlite_session_factory),
    )


@pytest.fixture
def threshold_constants() -> type[Threshold]:
    return Threshold
