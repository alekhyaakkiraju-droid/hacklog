"""Unit tests for hacklog.config."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from hacklog.config import ScoringConfig, load_config


LEGACY_WEIGHTS = {
    "hours_weight": 10,
    "days_weight": 10,
    "server_weight": 15,
    "success_weight": 35,
    "vpn_weight": 0,
    "internal_weight": 10,
    "external_weight": 15,
    "ip_weight": 15,
}

LEGACY_THRESHOLDS = {
    "critical_threshold": 50,
    "scary_threshold": 30,
    "scare_count_limit": 2,
    "scare_date_expire_days": 1,
}


def _set_required_smtp_env(
    monkeypatch: pytest.MonkeyPatch,
    *,
    include_host: bool = True,
) -> None:
    monkeypatch.setenv("HACKLOG_SMTP_USER", "alerts@example.com")
    monkeypatch.setenv("HACKLOG_SMTP_PASSWORD", "secret-password")
    monkeypatch.setenv("HACKLOG_SMTP_SENDER", "alerts@example.com")
    monkeypatch.setenv("HACKLOG_ALERT_RECIPIENT", "soc@example.com")
    if include_host:
        monkeypatch.setenv("HACKLOG_SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("HACKLOG_SMTP_PORT", "587")


@pytest.fixture(autouse=True)
def isolated_hacklog_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "HACKLOG_SMTP_USER",
        "HACKLOG_SMTP_PASSWORD",
        "HACKLOG_SMTP_SENDER",
        "HACKLOG_SMTP_HOST",
        "HACKLOG_SMTP_PORT",
        "HACKLOG_ALERT_RECIPIENT",
        "HACKLOG_SYSLOG_PORT",
        "HACKLOG_SCORING_HOURS_WEIGHT",
    ):
        monkeypatch.delenv(key, raising=False)


def test_scoring_defaults_match_legacy_constants() -> None:
    scoring = ScoringConfig()
    for field, expected in {**LEGACY_WEIGHTS, **LEGACY_THRESHOLDS}.items():
        assert getattr(scoring, field) == expected


def test_load_config_applies_scoring_defaults_with_required_smtp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_smtp_env(monkeypatch)
    config = load_config()

    for field, expected in {**LEGACY_WEIGHTS, **LEGACY_THRESHOLDS}.items():
        assert getattr(config.scoring, field) == expected


def test_env_var_override_for_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_smtp_env(monkeypatch)
    monkeypatch.setenv("HACKLOG_SMTP_HOST", "mail.internal.example")
    monkeypatch.setenv("HACKLOG_SMTP_PORT", "2525")

    config = load_config()

    assert config.smtp.host == "mail.internal.example"
    assert config.smtp.port == 2525
    assert config.smtp.username == "alerts@example.com"
    assert config.smtp.recipient == "soc@example.com"


def test_missing_smtp_password_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HACKLOG_SMTP_USER", "alerts@example.com")
    monkeypatch.setenv("HACKLOG_SMTP_SENDER", "alerts@example.com")
    monkeypatch.setenv("HACKLOG_ALERT_RECIPIENT", "soc@example.com")
    monkeypatch.delenv("HACKLOG_SMTP_PASSWORD", raising=False)

    with pytest.raises(ValidationError) as exc_info:
        load_config()

    message = str(exc_info.value)
    assert "HACKLOG_SMTP_PASSWORD" in message


def test_empty_smtp_password_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HACKLOG_SMTP_USER", "alerts@example.com")
    monkeypatch.setenv("HACKLOG_SMTP_PASSWORD", "   ")
    monkeypatch.setenv("HACKLOG_SMTP_SENDER", "alerts@example.com")
    monkeypatch.setenv("HACKLOG_ALERT_RECIPIENT", "soc@example.com")

    with pytest.raises(ValidationError) as exc_info:
        load_config()

    message = str(exc_info.value)
    assert "HACKLOG_SMTP_PASSWORD" in message
    assert "environment variable is required" in message


def test_invalid_port_raises_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_smtp_env(monkeypatch)
    monkeypatch.setenv("HACKLOG_SMTP_PORT", "-1")

    with pytest.raises(ValidationError) as exc_info:
        load_config()

    assert "port" in str(exc_info.value).lower()


def test_invalid_scoring_weight_raises_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_smtp_env(monkeypatch)
    monkeypatch.setenv("HACKLOG_SCORING_HOURS_WEIGHT", "101")

    with pytest.raises(ValidationError) as exc_info:
        load_config()

    assert "hours_weight" in str(exc_info.value)


def test_yaml_file_loading(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_smtp_env(monkeypatch, include_host=False)
    yaml_path = tmp_path / "hacklog.yaml"
    yaml_path.write_text(
        "\n".join(
            [
                "syslog:",
                "  bind_address: 0.0.0.0",
                "  port: 1514",
                "scoring:",
                "  hours_weight: 12",
                "smtp:",
                "  host: yaml-smtp.example",
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(yaml_path)

    assert config.syslog.bind_address == "0.0.0.0"
    assert config.syslog.port == 1514
    assert config.scoring.hours_weight == 12
    assert config.smtp.host == "yaml-smtp.example"


def test_env_vars_override_yaml(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_smtp_env(monkeypatch)
    monkeypatch.setenv("HACKLOG_SYSLOG_PORT", "9999")
    monkeypatch.setenv("HACKLOG_SCORING_HOURS_WEIGHT", "20")

    yaml_path = tmp_path / "hacklog.yaml"
    yaml_path.write_text(
        "\n".join(
            [
                "syslog:",
                "  port: 1514",
                "scoring:",
                "  hours_weight: 12",
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(yaml_path)

    assert config.syslog.port == 9999
    assert config.scoring.hours_weight == 20
