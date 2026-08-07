"""Unit and integration tests for hacklog.validators."""

from __future__ import annotations

import pytest

from hacklog.entities import IpAddress, SyslogMsg
from hacklog.metrics import messages_dropped_total
from hacklog.parse import Parser
from hacklog.validators import (
    FieldValidationResult,
    sanitize_for_log,
    validate_hostname,
    validate_ip_address,
    validate_parsed_fields,
    validate_username,
)
from tests.fixtures.injection_messages import (
    INJECTION_SYSLOG_FIXTURES,
    VALID_SYSLOG_FIXTURES,
)


@pytest.mark.parametrize(
    ("value", "expected_valid"),
    [
        ("alice", True),
        ("user_1", True),
        ("admin-user", True),
        ("admin'; DROP TABLE users;--", False),
        ("$(whoami)", False),
        ("admin)(|(password=*))", False),
        ("user\nname", False),
        ("user\x00name", False),
        ("", False),
    ],
)
def test_validate_username(value: str, expected_valid: bool) -> None:
    result = validate_username(value)
    assert isinstance(result, FieldValidationResult)
    assert result.valid is expected_valid


@pytest.mark.parametrize(
    ("value", "expected_valid"),
    [
        ("10.42.10.2", True),
        ("192.168.1.1", True),
        ("2001:db8::1", True),
        ("999.999.999.999", False),
        ("not-an-ip", False),
        ("10.0.0.1'; DROP TABLE users;--", False),
        ("10.0.0.1\n", False),
    ],
)
def test_validate_ip_address(value: str, expected_valid: bool) -> None:
    result = validate_ip_address(value)
    assert result.valid is expected_valid


@pytest.mark.parametrize(
    ("value", "expected_valid"),
    [
        ("prod-web-01", True),
        ("ae1-app80-prd", True),
        ("host.example.com", True),
        ("bad host", False),
        ("host;rm -rf /", False),
        ("host\nname", False),
    ],
)
def test_validate_hostname(value: str, expected_valid: bool) -> None:
    result = validate_hostname(value)
    assert result.valid is expected_valid


def test_validate_parsed_fields_increments_invalid_field_counter() -> None:
    before = messages_dropped_total.labels(
        reason="invalid_field"
    )._value.get()  # noqa: SLF001
    assert validate_parsed_fields("bad user", "10.0.0.1", "host1") is False
    after = messages_dropped_total.labels(
        reason="invalid_field"
    )._value.get()  # noqa: SLF001
    assert after - before == 1.0


def test_validate_parsed_fields_accepts_valid_triplet() -> None:
    assert validate_parsed_fields("alice", "10.42.10.2", "prod-web-01") is True


def test_sanitize_for_log_escapes_control_characters() -> None:
    assert "\\x00" in sanitize_for_log("a\x00b")


@pytest.mark.parametrize(
    ("ip_address", "vpn", "internal"),
    [
        ("10.42.1.5", True, False),
        ("10.24.1.5", False, True),
        ("10.26.1.5", False, True),
        ("172.16.1.5", False, True),
        ("203.0.113.5", False, False),
    ],
)
def test_ip_address_entity_checks_work_with_validated_ips(
    ip_address: str, vpn: bool, internal: bool
) -> None:
    assert validate_ip_address(ip_address).valid is True
    assert IpAddress.check_ip_for_vpn(ip_address) is vpn
    assert IpAddress.check_ip_for_internal(ip_address) is internal


@pytest.mark.parametrize(
    ("fixture_name", "expected_parsed"),
    [
        ("success_ssh", True),
        ("failure_ssh", True),
        ("sql_username", False),
        ("shell_username", False),
        ("ldap_username", False),
        ("null_byte_username", False),
        ("invalid_ip", False),
    ],
)
def test_parser_rejects_injection_payloads(
    fixture_name: str, expected_parsed: bool
) -> None:
    parser = Parser(validate_fields=True)
    fixtures = {**VALID_SYSLOG_FIXTURES, **INJECTION_SYSLOG_FIXTURES}
    message = SyslogMsg(fixtures[fixture_name], "127.0.0.1")
    event = parser.parse_log_line(message)
    if expected_parsed:
        assert event is not None
    else:
        assert event is None


def test_parser_integration_rejects_invalid_ip_before_database_layer() -> None:
    parser = Parser(validate_fields=True)
    before = messages_dropped_total.labels(
        reason="invalid_field"
    )._value.get()  # noqa: SLF001
    message = SyslogMsg(INJECTION_SYSLOG_FIXTURES["invalid_ip"], "127.0.0.1")
    assert parser.parse_log_line(message) is None
    after = messages_dropped_total.labels(
        reason="invalid_field"
    )._value.get()  # noqa: SLF001
    assert after - before >= 1.0
