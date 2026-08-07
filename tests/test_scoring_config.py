"""Tests verifying that ScoringEngine reads all weights and thresholds from ScoringConfig.

Covers acceptance criteria:
  - Default ScoringConfig values match the legacy hardcoded Weight/Threshold constants.
  - Changing HACKLOG_SCORING_CRITICAL_THRESHOLD causes alerts to trigger at the new threshold.
  - Changing HACKLOG_SCORING_HOURS_WEIGHT doubles the time-of-day contribution.
  - Custom configuration values change scoring behavior as expected.
"""

import math
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

from config import ScoringConfig  # noqa: E402
from entities import EventLog, User  # noqa: E402
from scoring import ScoringEngine  # noqa: E402

# ---------------------------------------------------------------------------
# Legacy constants (copied from entities.py Weight / Threshold for reference)
# ---------------------------------------------------------------------------
LEGACY_HOURS = 10
LEGACY_DAYS = 10
LEGACY_SERVER = 15
LEGACY_SUCCESS = 35
LEGACY_VPN = 0
LEGACY_INT = 10
LEGACY_EXT = 15
LEGACY_IP = 15
LEGACY_CRITICAL = 50
LEGACY_SCARY = 30
LEGACY_SCARECOUNT = 2
LEGACY_SCAREDATEEXPIRE = 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine(config: ScoringConfig | None = None) -> ScoringEngine:
    update_service = MagicMock()
    alert_service = MagicMock()
    # Set default mock frequencies so calculate_*_score methods return deterministic values
    update_service.update_and_return_hour_freq_for_user.return_value = 0.5
    update_service.update_and_return_day_freq_for_user.return_value = 0.5
    update_service.update_and_return_server_freq_for_user.return_value = 0.5
    update_service.update_and_return_ip_freq_for_user.return_value = 0.5
    return ScoringEngine(update_service, alert_service, config=config)


def _make_event_log(success: bool = False, ip: str = "10.0.0.1") -> EventLog:
    return EventLog(datetime(2026, 1, 15, 10, 0, 0), "testuser", ip, success, "prod-host")


def _subscore(freq: float) -> float:
    """Mirror of ScoringEngine.calculate_subscore logic."""
    val = math.log(freq, 2) * -10
    if val > 100:
        return 100.0
    return float(val) / 100


# ---------------------------------------------------------------------------
# Criterion: default ScoringConfig values match legacy hardcoded constants
# ---------------------------------------------------------------------------

def test_default_config_hours_weight_matches_legacy() -> None:
    config = ScoringConfig()
    assert config.hours_weight == LEGACY_HOURS


def test_default_config_days_weight_matches_legacy() -> None:
    config = ScoringConfig()
    assert config.days_weight == LEGACY_DAYS


def test_default_config_server_weight_matches_legacy() -> None:
    config = ScoringConfig()
    assert config.server_weight == LEGACY_SERVER


def test_default_config_success_weight_matches_legacy() -> None:
    config = ScoringConfig()
    assert config.success_weight == LEGACY_SUCCESS


def test_default_config_vpn_weight_matches_legacy() -> None:
    config = ScoringConfig()
    assert config.vpn_weight == LEGACY_VPN


def test_default_config_internal_weight_matches_legacy() -> None:
    config = ScoringConfig()
    assert config.internal_weight == LEGACY_INT


def test_default_config_external_weight_matches_legacy() -> None:
    config = ScoringConfig()
    assert config.external_weight == LEGACY_EXT


def test_default_config_ip_weight_matches_legacy() -> None:
    config = ScoringConfig()
    assert config.ip_weight == LEGACY_IP


def test_default_config_critical_threshold_matches_legacy() -> None:
    config = ScoringConfig()
    assert config.critical_threshold == LEGACY_CRITICAL


def test_default_config_scary_threshold_matches_legacy() -> None:
    config = ScoringConfig()
    assert config.scary_threshold == LEGACY_SCARY


def test_default_config_scare_count_limit_matches_legacy() -> None:
    config = ScoringConfig()
    assert config.scare_count_limit == LEGACY_SCARECOUNT


def test_default_config_scare_date_expire_days_matches_legacy() -> None:
    config = ScoringConfig()
    assert config.scare_date_expire_days == LEGACY_SCAREDATEEXPIRE


# ---------------------------------------------------------------------------
# Criterion: golden score with default config matches hand-calculated legacy result
# ---------------------------------------------------------------------------

def test_golden_score_failed_login_internal_ip_with_default_config() -> None:
    """
    Known scenario: failed login, internal IP (10.x), freq=0.5 on all dimensions.

    Expected with legacy constants:
      success_score     = 35  (failed login, Weight.SUCCESS=35)
      ip_location_score = 10  (internal IP, Weight.INT=10)
      hours_score       = 0.1 * 10 = 1.0
      days_score        = 0.1 * 10 = 1.0
      server_score      = 0.1 * 15 = 1.5
      ip_score          = 0.1 * 15 = 1.5
      total             = int(35 + 10 + 1.0 + 1.0 + 1.5 + 1.5) = int(50.0) = 50
    """
    engine = _make_engine()  # default config
    event_log = _make_event_log(success=False, ip="10.0.0.1")
    score, dims = engine.calculate_new_score(event_log)

    expected = int(
        LEGACY_SUCCESS
        + LEGACY_INT
        + _subscore(0.5) * LEGACY_HOURS
        + _subscore(0.5) * LEGACY_DAYS
        + _subscore(0.5) * LEGACY_SERVER
        + _subscore(0.5) * LEGACY_IP
    )
    assert score == expected


def test_golden_score_successful_login_external_ip_with_default_config() -> None:
    """
    Known scenario: successful login, external IP, freq=0.5 on all dimensions.

    Expected with legacy constants:
      success_score     = 0   (successful login)
      ip_location_score = 15  (external IP, Weight.EXT=15)
      hours_score       = 0.1 * 10 = 1.0
      days_score        = 0.1 * 10 = 1.0
      server_score      = 0.1 * 15 = 1.5
      ip_score          = 0.1 * 15 = 1.5
      total             = int(0 + 15 + 1.0 + 1.0 + 1.5 + 1.5) = int(20.0) = 20
    """
    engine = _make_engine()  # default config
    event_log = _make_event_log(success=True, ip="203.0.113.1")  # external public IP
    score, dims = engine.calculate_new_score(event_log)

    expected = int(
        0
        + LEGACY_EXT
        + _subscore(0.5) * LEGACY_HOURS
        + _subscore(0.5) * LEGACY_DAYS
        + _subscore(0.5) * LEGACY_SERVER
        + _subscore(0.5) * LEGACY_IP
    )
    assert score == expected


# ---------------------------------------------------------------------------
# Criterion: changing CRITICAL_THRESHOLD from 50 to 40 causes alert at score 41
# ---------------------------------------------------------------------------

def test_lowered_critical_threshold_triggers_alert_at_41() -> None:
    """HACKLOG_SCORING_CRITICAL_THRESHOLD=40 → score of 41 triggers an immediate alert."""
    config = ScoringConfig(critical_threshold=40)
    update_service = MagicMock()
    alert_service = MagicMock()
    user = User("testuser", datetime(2026, 1, 15, 10, 0, 0), 0)
    update_service.fetch_user.return_value = user

    engine = ScoringEngine(update_service, alert_service, config=config)
    # Override calculate_new_score to return exactly 41
    engine.calculate_new_score = MagicMock(return_value=(41, {}))  # type: ignore[method-assign]

    event_log = _make_event_log()
    engine.process_event_log(event_log)

    alert_service.send_email_alert.assert_called_once_with(user, event_log)


def test_default_critical_threshold_does_not_alert_at_41() -> None:
    """With default threshold (50), a score of 41 does NOT trigger an immediate alert."""
    config = ScoringConfig()  # critical_threshold=50
    update_service = MagicMock()
    alert_service = MagicMock()
    user = User("testuser", datetime(2026, 1, 15, 10, 0, 0), 0)
    update_service.fetch_user.return_value = user

    engine = ScoringEngine(update_service, alert_service, config=config)
    engine.calculate_new_score = MagicMock(return_value=(41, {}))  # type: ignore[method-assign]

    event_log = _make_event_log()
    engine.process_event_log(event_log)

    alert_service.send_email_alert.assert_not_called()


def test_critical_threshold_boundary_at_exact_value_does_not_alert() -> None:
    """Score equal to critical_threshold (not strictly greater) does NOT trigger alert."""
    config = ScoringConfig(critical_threshold=50)
    update_service = MagicMock()
    alert_service = MagicMock()
    user = User("testuser", datetime(2026, 1, 15, 10, 0, 0), 0)
    update_service.fetch_user.return_value = user

    engine = ScoringEngine(update_service, alert_service, config=config)
    engine.calculate_new_score = MagicMock(return_value=(50, {}))  # type: ignore[method-assign]

    event_log = _make_event_log()
    engine.process_event_log(event_log)

    alert_service.send_email_alert.assert_not_called()


def test_critical_threshold_one_above_boundary_triggers_alert() -> None:
    """Score strictly greater than critical_threshold triggers alert."""
    config = ScoringConfig(critical_threshold=50)
    update_service = MagicMock()
    alert_service = MagicMock()
    user = User("testuser", datetime(2026, 1, 15, 10, 0, 0), 0)
    update_service.fetch_user.return_value = user

    engine = ScoringEngine(update_service, alert_service, config=config)
    engine.calculate_new_score = MagicMock(return_value=(51, {}))  # type: ignore[method-assign]

    event_log = _make_event_log()
    engine.process_event_log(event_log)

    alert_service.send_email_alert.assert_called_once_with(user, event_log)


# ---------------------------------------------------------------------------
# Criterion: changing HOURS_WEIGHT from 10 to 20 doubles hours score contribution
# ---------------------------------------------------------------------------

def test_doubled_hours_weight_doubles_hours_score_contribution() -> None:
    """HACKLOG_SCORING_HOURS_WEIGHT=20 doubles the time-of-day contribution vs default."""
    freq = 0.25  # arbitrary but deterministic frequency

    default_engine = _make_engine(ScoringConfig(hours_weight=10))
    default_engine._update_service.update_and_return_hour_freq_for_user.return_value = freq
    event_log = _make_event_log()
    default_score = default_engine.calculate_hours_score(event_log)

    doubled_engine = _make_engine(ScoringConfig(hours_weight=20))
    doubled_engine._update_service.update_and_return_hour_freq_for_user.return_value = freq
    doubled_score = doubled_engine.calculate_hours_score(event_log)

    assert doubled_score == pytest.approx(default_score * 2, rel=1e-6)


def test_custom_hours_weight_zero_eliminates_hours_contribution() -> None:
    """HACKLOG_SCORING_HOURS_WEIGHT=0 removes all time-of-day contribution."""
    engine = _make_engine(ScoringConfig(hours_weight=0))
    engine._update_service.update_and_return_hour_freq_for_user.return_value = 0.25
    event_log = _make_event_log()
    assert engine.calculate_hours_score(event_log) == 0.0


# ---------------------------------------------------------------------------
# Criterion: other custom weight changes affect scoring as expected
# ---------------------------------------------------------------------------

def test_custom_success_weight_changes_failed_login_score() -> None:
    """Changing success_weight changes the penalty for failed logins."""
    engine_default = _make_engine(ScoringConfig(success_weight=35))
    engine_custom = _make_engine(ScoringConfig(success_weight=50))

    assert engine_default.calculate_success_score(False) == 35
    assert engine_custom.calculate_success_score(False) == 50
    # Successful login always scores 0 regardless of weight
    assert engine_default.calculate_success_score(True) == 0
    assert engine_custom.calculate_success_score(True) == 0


def test_custom_external_weight_changes_external_ip_score() -> None:
    """Changing external_weight changes the penalty for external source IPs."""
    engine_default = _make_engine(ScoringConfig(external_weight=15))
    engine_custom = _make_engine(ScoringConfig(external_weight=30))

    external_ip = "203.0.113.1"
    assert engine_default.calculate_ip_location_score(external_ip) == 15
    assert engine_custom.calculate_ip_location_score(external_ip) == 30


def test_custom_internal_weight_changes_internal_ip_score() -> None:
    """Changing internal_weight changes the penalty for internal source IPs."""
    engine_default = _make_engine(ScoringConfig(internal_weight=10))
    engine_custom = _make_engine(ScoringConfig(internal_weight=5))

    internal_ip = "10.0.0.1"
    assert engine_default.calculate_ip_location_score(internal_ip) == 10
    assert engine_custom.calculate_ip_location_score(internal_ip) == 5


def test_custom_vpn_weight_changes_vpn_ip_score() -> None:
    """Changing vpn_weight changes the score for VPN source IPs."""
    engine_zero = _make_engine(ScoringConfig(vpn_weight=0))
    engine_ten = _make_engine(ScoringConfig(vpn_weight=10))

    # 127.x.x.x is treated as VPN by IpAddress.check_ip_for_vpn
    # Use a loopback address which is recognised as VPN in the IpAddress helper
    vpn_ip = "127.0.0.1"
    assert engine_zero.calculate_ip_location_score(vpn_ip) == 0
    assert engine_ten.calculate_ip_location_score(vpn_ip) == 10


def test_custom_days_weight_changes_days_score() -> None:
    """Changing days_weight changes the day-of-week anomaly contribution."""
    freq = 0.5
    engine_default = _make_engine(ScoringConfig(days_weight=10))
    engine_default._update_service.update_and_return_day_freq_for_user.return_value = freq

    engine_custom = _make_engine(ScoringConfig(days_weight=20))
    engine_custom._update_service.update_and_return_day_freq_for_user.return_value = freq

    event_log = _make_event_log()
    default_score = engine_default.calculate_days_score(event_log)
    custom_score = engine_custom.calculate_days_score(event_log)

    assert custom_score == pytest.approx(default_score * 2, rel=1e-6)


def test_custom_server_weight_changes_server_score() -> None:
    """Changing server_weight changes the server access anomaly contribution."""
    freq = 0.5
    engine_default = _make_engine(ScoringConfig(server_weight=15))
    engine_default._update_service.update_and_return_server_freq_for_user.return_value = freq

    engine_custom = _make_engine(ScoringConfig(server_weight=30))
    engine_custom._update_service.update_and_return_server_freq_for_user.return_value = freq

    event_log = _make_event_log()
    default_score = engine_default.calculate_server_score(event_log)
    custom_score = engine_custom.calculate_server_score(event_log)

    assert custom_score == pytest.approx(default_score * 2, rel=1e-6)


def test_custom_ip_weight_changes_ip_score() -> None:
    """Changing ip_weight changes the source IP frequency anomaly contribution."""
    freq = 0.5
    engine_default = _make_engine(ScoringConfig(ip_weight=15))
    engine_default._update_service.update_and_return_ip_freq_for_user.return_value = freq

    engine_custom = _make_engine(ScoringConfig(ip_weight=30))
    engine_custom._update_service.update_and_return_ip_freq_for_user.return_value = freq

    event_log = _make_event_log()
    default_score = engine_default.calculate_ip_score(event_log)
    custom_score = engine_custom.calculate_ip_score(event_log)

    assert custom_score == pytest.approx(default_score * 2, rel=1e-6)


# ---------------------------------------------------------------------------
# Criterion: scary threshold and scare count limit are configurable
# ---------------------------------------------------------------------------

def test_custom_scary_threshold_changes_scare_count_increment() -> None:
    """Changing scary_threshold determines when scare count is incremented."""
    config_low = ScoringConfig(scary_threshold=20, critical_threshold=100)
    update_service = MagicMock()
    alert_service = MagicMock()
    user = User("testuser", datetime(2026, 1, 15, 10, 0, 0), 0)
    update_service.fetch_user.return_value = user
    update_service.update_user_scare_count.return_value = user

    engine = ScoringEngine(update_service, alert_service, config=config_low)
    # Score of 25: above scary_threshold=20, below critical_threshold=100
    engine.calculate_new_score = MagicMock(return_value=(25, {}))  # type: ignore[method-assign]

    event_log = _make_event_log()
    engine.process_event_log(event_log)

    update_service.update_user_scare_count.assert_called_once()


def test_scare_count_limit_controls_when_alert_fires_on_repeated_scares() -> None:
    """When scare_count >= scare_count_limit and score > scary_threshold, alert fires."""
    config = ScoringConfig(scary_threshold=30, critical_threshold=100, scare_count_limit=3)
    update_service = MagicMock()
    alert_service = MagicMock()
    # User already has scare_count=3 (at the limit)
    user = User("testuser", datetime(2026, 1, 15, 10, 0, 0), 0)
    user.scare_count = 3
    update_service.fetch_user.return_value = user
    update_service.update_user_scare_count.return_value = user

    engine = ScoringEngine(update_service, alert_service, config=config)
    # Score between scary (30) and critical (100)
    engine.calculate_new_score = MagicMock(return_value=(45, {}))  # type: ignore[method-assign]

    event_log = _make_event_log()
    engine.process_event_log(event_log)

    alert_service.send_email_alert.assert_called_once_with(user, event_log)


# ---------------------------------------------------------------------------
# Criterion: ScoringEngine uses default ScoringConfig when no config is passed
# ---------------------------------------------------------------------------

def test_scoring_engine_uses_default_config_when_not_provided() -> None:
    """ScoringEngine instantiated without config uses ScoringConfig() defaults."""
    engine = _make_engine(config=None)
    assert engine.config.hours_weight == LEGACY_HOURS
    assert engine.config.critical_threshold == LEGACY_CRITICAL
    assert engine.config.success_weight == LEGACY_SUCCESS
