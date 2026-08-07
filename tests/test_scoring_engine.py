"""Unit tests for ScoringEngine dependency injection."""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_HACKLOG_DIR = _TESTS_DIR.parent / "hacklog"
for _path in (_HACKLOG_DIR, _TESTS_DIR.parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from entities import EventLog, Threshold, User  # noqa: E402
from scoring import ScoringEngine  # noqa: E402

@pytest.fixture
def event_log() -> EventLog:
    return EventLog(
        datetime(2026, 1, 15, 10, 0, 0), "nrhine", "10.42.10.2", False, "prod-host"
    )

@pytest.fixture
def mock_services():
    update_service = MagicMock()
    alert_service = MagicMock()
    user = User("nrhine", datetime(2026, 1, 15, 10, 0, 0), 0)
    update_service.fetch_user.return_value = user
    update_service.update_and_return_hour_freq_for_user.return_value = 0.5
    update_service.update_and_return_day_freq_for_user.return_value = 0.5
    update_service.update_and_return_server_freq_for_user.return_value = 0.5
    update_service.update_and_return_ip_freq_for_user.return_value = 0.5
    return update_service, alert_service, user

def test_scoring_engine_instantiates_with_mock_services(mock_services) -> None:
    update_service, alert_service, _user = mock_services
    engine = ScoringEngine(update_service, alert_service)
    assert engine is not None

def test_process_event_log_audits_and_updates_score(mock_services, event_log) -> None:
    update_service, alert_service, user = mock_services
    engine = ScoringEngine(update_service, alert_service)
    engine.process_event_log(event_log)
    update_service.audit_event_log.assert_called_once_with(event_log)
    update_service.fetch_user.assert_called_once_with(event_log)
    update_service.update_user_score.assert_called_once()
    alert_service.send_email_alert.assert_not_called()

def test_critical_score_triggers_alert(mock_services, event_log) -> None:
    update_service, alert_service, user = mock_services
    engine = ScoringEngine(update_service, alert_service)
    engine.calculate_new_score = MagicMock(return_value=(Threshold.CRITICAL + 1, {}))  # type: ignore[method-assign]
    engine.process_event_log(event_log)
    alert_service.send_email_alert.assert_called_once_with(user, event_log)

def test_calculate_subscore_bounds_high_frequency() -> None:
    assert ScoringEngine.calculate_subscore(1.0) <= 1.0

def test_calculate_success_score_failure_adds_weight(event_log) -> None:
    event_log.success = False
    update_service = MagicMock()
    alert_service = MagicMock()
    engine = ScoringEngine(update_service, alert_service)
    score = engine.calculate_success_score(event_log.success)
    assert score > 0

def test_calculate_success_score_success_is_zero(event_log) -> None:
    event_log.success = True
    update_service = MagicMock()
    alert_service = MagicMock()
    engine = ScoringEngine(update_service, alert_service)
    assert engine.calculate_success_score(event_log.success) == 0
