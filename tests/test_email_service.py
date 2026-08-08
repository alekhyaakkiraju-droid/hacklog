"""Unit tests for AlertService credential loading."""

import pytest
from pydantic import ValidationError

from hacklog.alerting import AlertService
from hacklog.config import load_config, load_config_or_exit


def _set_test_smtp_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HACKLOG_SMTP_USER", "test@example.com")
    monkeypatch.setenv("HACKLOG_SMTP_PASSWORD", "test-password")
    monkeypatch.setenv("HACKLOG_SMTP_SENDER", "alerts@example.com")
    monkeypatch.setenv("HACKLOG_ALERT_RECIPIENT", "soc@example.com")
    monkeypatch.setenv("HACKLOG_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("HACKLOG_SMTP_PORT", "587")


@pytest.fixture(autouse=True)
def isolated_smtp_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "HACKLOG_SMTP_USER",
        "HACKLOG_SMTP_PASSWORD",
        "HACKLOG_SMTP_SENDER",
        "HACKLOG_ALERT_RECIPIENT",
        "HACKLOG_SMTP_HOST",
        "HACKLOG_SMTP_PORT",
    ):
        monkeypatch.delenv(key, raising=False)


def test_alert_service_initialization_succeeds_with_env_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_test_smtp_env(monkeypatch)
    smtp_config = load_config().smtp

    service = AlertService(smtp_config)

    assert service.from_address == "alerts@example.com"
    assert service.recipient == "soc@example.com"
    assert service.mail_server is None


def test_alert_service_initialization_fails_without_smtp_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HACKLOG_SMTP_USER", "test@example.com")
    monkeypatch.setenv("HACKLOG_SMTP_SENDER", "alerts@example.com")
    monkeypatch.setenv("HACKLOG_ALERT_RECIPIENT", "soc@example.com")
    monkeypatch.delenv("HACKLOG_SMTP_PASSWORD", raising=False)

    with pytest.raises(ValidationError) as exc_info:
        load_config()

    assert "HACKLOG_SMTP_PASSWORD" in str(exc_info.value)


def test_startup_exits_when_smtp_password_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HACKLOG_SMTP_USER", "test@example.com")
    monkeypatch.setenv("HACKLOG_SMTP_SENDER", "alerts@example.com")
    monkeypatch.setenv("HACKLOG_ALERT_RECIPIENT", "soc@example.com")
    monkeypatch.delenv("HACKLOG_SMTP_PASSWORD", raising=False)

    with pytest.raises(SystemExit) as exc_info:
        load_config_or_exit()

    assert (
        str(exc_info.value) == "HACKLOG_SMTP_PASSWORD environment variable is required"
    )


def test_alert_service_requires_smtp_config_object() -> None:
    with pytest.raises(TypeError):
        AlertService(None)

    with pytest.raises(TypeError):
        AlertService(object())
