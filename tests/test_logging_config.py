"""Unit tests for hacklog.logging_config."""

from __future__ import annotations

import json
import logging

import pytest
import structlog
from pydantic.types import SecretStr

from hacklog.logging_config import (
    clear_context,
    configure_logging,
    get_logger,
    parse_json_log_line,
    render_event_dict,
)


@pytest.fixture(autouse=True)
def reset_logging() -> None:
    clear_context()
    logging.getLogger().handlers.clear()
    structlog.reset_defaults()


def test_structlog_configuration_produces_valid_json(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(level=logging.INFO)
    logger = get_logger("test")
    logger.info("configuration_check", operation="validate_json")

    line = capsys.readouterr().out.strip()
    payload = parse_json_log_line(line)

    assert payload["event"] == "configuration_check"
    assert payload["component"] == "test"
    assert payload["operation"] == "validate_json"
    assert "timestamp" in payload
    assert payload["level"] == "info"


def test_render_event_dict_is_valid_json() -> None:
    output = render_event_dict(
        {
            "event": "sample",
            "component": "algorithm",
            "operation": "calculate_score",
            "level": "debug",
        }
    )
    payload = json.loads(output)
    assert payload["component"] == "algorithm"


def test_scoring_operation_log_contains_expected_fields(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(level=logging.DEBUG)
    logger = get_logger("algorithm")
    logger.debug(
        "score_calculated",
        operation="calculate_score",
        username="alice",
        source_ip="10.0.0.5",
        score=42,
    )

    payload = parse_json_log_line(capsys.readouterr().out.strip())

    assert payload["component"] == "algorithm"
    assert payload["operation"] == "calculate_score"
    assert payload["username"] == "alice"
    assert payload["source_ip"] == "10.0.0.5"
    assert payload["score"] == 42


def test_credentials_are_never_logged(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(level=logging.INFO)
    logger = get_logger("smtp")

    secret_password = "SuperSecretSMTPPassword123"
    logger.info(
        "smtp_config_loaded",
        operation="load_smtp_config",
        host="smtp.example.com",
        username="alerts@example.com",
        password=SecretStr(secret_password),
        smtp_password=secret_password,
    )

    output = capsys.readouterr().out
    assert secret_password not in output
    assert "SuperSecret" not in output

    payload = parse_json_log_line(output.strip())
    assert payload["password"] == "***REDACTED***"
    assert payload["smtp_password"] == "***REDACTED***"


def test_pii_masking_redacts_debug_level_identifiers(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(level=logging.DEBUG, mask_pii=True)
    logger = get_logger("algorithm")
    logger.debug(
        "score_calculated",
        operation="calculate_score",
        username="alice",
        source_ip="10.0.0.5",
        score=42,
    )

    payload = parse_json_log_line(capsys.readouterr().out.strip())
    assert payload["username"] != "alice"
    assert payload["source_ip"] != "10.0.0.5"


def test_pii_not_masked_for_info_level_alert_logs(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(level=logging.INFO, mask_pii=True)
    logger = get_logger("algorithm")
    logger.info(
        "alert_triggered",
        operation="process_alert",
        username="alice",
        source_ip="10.0.0.5",
        score=75,
    )

    payload = parse_json_log_line(capsys.readouterr().out.strip())
    assert payload["username"] == "alice"
    assert payload["source_ip"] == "10.0.0.5"
