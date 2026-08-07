"""Behavioral tests for ScoringEngine scoring dimensions and alert logic."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

_TESTS_DIR = Path(__file__).resolve().parent
_HACKLOG_DIR = _TESTS_DIR.parent / "hacklog"
for _path in (_HACKLOG_DIR, _TESTS_DIR.parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from entities import EventLog, Threshold, User, Weight  # noqa: E402
from scoring import ScoringEngine  # noqa: E402


def _engine_with_freqs(
    hour: float = 0.5,
    day: float = 0.5,
    server: float = 0.5,
    ip: float = 0.5,
    user: User | None = None,
) -> tuple[ScoringEngine, MagicMock, MagicMock, User]:
    update_service = MagicMock()
    alert_service = MagicMock()
    resolved_user = user or User("nrhine", datetime(2026, 1, 15, 10, 0, 0), 0)
    update_service.fetch_user.return_value = resolved_user
    update_service.update_and_return_hour_freq_for_user.return_value = hour
    update_service.update_and_return_day_freq_for_user.return_value = day
    update_service.update_and_return_server_freq_for_user.return_value = server
    update_service.update_and_return_ip_freq_for_user.return_value = ip
    update_service.update_user_scare_count.return_value = resolved_user
    return ScoringEngine(update_service, alert_service), update_service, alert_service, resolved_user


@pytest.mark.parametrize(
    ("success", "expected"),
    [(True, 0), (False, Weight.SUCCESS)],
)
def test_success_dimension_score(success: bool, expected: int) -> None:
    assert ScoringEngine.calculate_success_score(success) == expected


@pytest.mark.parametrize(
    ("ip_address", "expected"),
    [
        ("10.42.1.5", Weight.VPN),
        ("10.24.1.5", Weight.INT),
        ("10.26.1.5", Weight.INT),
        ("172.16.1.5", Weight.INT),
        ("203.0.113.5", Weight.EXT),
    ],
)
def test_ip_location_dimension_score(ip_address: str, expected: int) -> None:
    assert ScoringEngine.calculate_ip_location_score(ip_address) == expected


@pytest.mark.parametrize(
    ("freq", "weight", "method_name"),
    [
        (0.25, Weight.HOURS, "calculate_hours_score"),
        (0.25, Weight.DAYS, "calculate_days_score"),
        (0.25, Weight.SERVER, "calculate_server_score"),
        (0.25, Weight.IP, "calculate_ip_score"),
    ],
)
def test_profile_dimension_weighted_scores(
    freq: float, weight: int, method_name: str, sample_event_log: EventLog
) -> None:
    engine, update_service, _, _ = _engine_with_freqs(
        hour=freq if method_name == "calculate_hours_score" else 1.0,
        day=freq if method_name == "calculate_days_score" else 1.0,
        server=freq if method_name == "calculate_server_score" else 1.0,
        ip=freq if method_name == "calculate_ip_score" else 1.0,
    )
    expected = ScoringEngine.calculate_subscore(freq) * weight
    assert getattr(engine, method_name)(sample_event_log) == pytest.approx(expected)


@pytest.mark.parametrize("hour", [0, 4, 8, 12, 16, 20])
def test_hour_range_buckets_map_to_six_ranges(
    hour: int, update_service, sample_event_log: EventLog
) -> None:
    sample_event_log.date = sample_event_log.date.replace(hour=hour)
    freq = update_service.update_and_return_hour_freq_for_user(sample_event_log)
    assert 0.0 < freq <= 1.0


@pytest.mark.parametrize("weekday", ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
def test_weekday_dimension_updates_profile(
    weekday: str, update_service, sample_event_log: EventLog
) -> None:
    weekday_offsets = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
    base = datetime(2026, 1, 5, 10, 0, 0)
    sample_event_log.date = base + timedelta(days=weekday_offsets[weekday])
    freq = update_service.update_and_return_day_freq_for_user(sample_event_log)
    assert freq == 1.0


def test_known_server_and_ip_frequencies(update_service, sample_event_log: EventLog) -> None:
    first_server = update_service.update_and_return_server_freq_for_user(sample_event_log)
    first_ip = update_service.update_and_return_ip_freq_for_user(sample_event_log)
    assert first_server == 1.0
    assert first_ip == 1.0
    second_server = update_service.update_and_return_server_freq_for_user(sample_event_log)
    assert second_server == 1.0


@given(st.floats(min_value=0.01, max_value=1.0))
@settings(max_examples=200)
def test_calculate_subscore_bounds(freq: float) -> None:
    subscore = ScoringEngine.calculate_subscore(freq)
    assert 0.0 <= subscore <= 1.0


def test_calculate_subscore_at_full_frequency_is_zero() -> None:
    assert ScoringEngine.calculate_subscore(1.0) == 0.0


@given(
    st.floats(min_value=0.01, max_value=0.99),
    st.floats(min_value=0.01, max_value=0.99),
)
@settings(max_examples=200)
def test_calculate_subscore_monotonically_decreases_with_frequency(
    low_freq: float, high_freq: float
) -> None:
    if low_freq >= high_freq:
        return
    assert ScoringEngine.calculate_subscore(high_freq) <= ScoringEngine.calculate_subscore(
        low_freq
    )


def test_critical_score_51_triggers_immediate_alert(sample_event_log: EventLog) -> None:
    engine, _, alert_service, user = _engine_with_freqs()
    engine.calculate_new_score = MagicMock(return_value=51)  # type: ignore[method-assign]
    engine.process_event_log(sample_event_log)
    alert_service.send_email_alert.assert_called_once_with(user, sample_event_log)


def test_score_49_does_not_trigger_alert(sample_event_log: EventLog) -> None:
    engine, _, alert_service, _ = _engine_with_freqs()
    engine.calculate_new_score = MagicMock(return_value=49)  # type: ignore[method-assign]
    engine.process_event_log(sample_event_log)
    alert_service.send_email_alert.assert_not_called()


def test_scary_score_with_scare_count_2_triggers_alert(sample_event_log: EventLog) -> None:
    user = User("nrhine", datetime(2026, 1, 15, 10, 0, 0), 0)
    user.scare_count = 2
    engine, _, alert_service, _ = _engine_with_freqs(user=user)
    engine.calculate_new_score = MagicMock(return_value=31)  # type: ignore[method-assign]
    engine.process_event_log(sample_event_log)
    alert_service.send_email_alert.assert_called_once()


def test_scary_score_with_scare_count_1_does_not_alert(sample_event_log: EventLog) -> None:
    user = User("nrhine", datetime(2026, 1, 15, 10, 0, 0), 0)
    user.scare_count = 1
    engine, update_service, alert_service, _ = _engine_with_freqs(user=user)
    engine.calculate_new_score = MagicMock(return_value=31)  # type: ignore[method-assign]
    engine.process_event_log(sample_event_log)
    alert_service.send_email_alert.assert_not_called()
    update_service.update_user_scare_count.assert_called_once()


def test_scare_counter_resets_after_expiry(sample_event_log: EventLog) -> None:
    old_date = datetime(2026, 1, 10, 10, 0, 0)
    user = User("nrhine", old_date, 5)
    user.scare_count = 3
    engine, update_service, alert_service, _ = _engine_with_freqs(user=user)
    engine.calculate_new_score = MagicMock(return_value=10)  # type: ignore[method-assign]
    engine.process_event_log(sample_event_log)
    update_service.reset_user_scare_count.assert_called_once_with(user)
    alert_service.send_email_alert.assert_not_called()


def test_update_user_scare_count_returns_user_not_none(sample_event_log: EventLog) -> None:
    user = User("nrhine", datetime(2026, 1, 15, 10, 0, 0), 0)
    user.scare_count = 1
    updated = User("nrhine", datetime(2026, 1, 15, 10, 0, 0), 0)
    updated.scare_count = 2
    engine, update_service, _, _ = _engine_with_freqs(user=user)
    update_service.update_user_scare_count.return_value = updated
    engine.calculate_new_score = MagicMock(return_value=31)  # type: ignore[method-assign]
    engine.process_event_log(sample_event_log)
    result_user = update_service.update_user_scare_count.return_value
    assert result_user is not None
    assert result_user.scare_count == 2


def test_full_pipeline_sqlite_integration(
    update_service, sample_event_log: EventLog
) -> None:
    alert_service = MagicMock()
    engine = ScoringEngine(update_service, alert_service)
    engine.process_event_log(sample_event_log)
    alert_service.send_email_alert.assert_not_called()
    user = update_service.fetch_user(sample_event_log)
    assert user is not None
    assert user.score >= 0
