"""Behavioral parser tests for all supported syslog message formats."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_HACKLOG_DIR = _TESTS_DIR.parent / "hacklog"
for _path in (_HACKLOG_DIR, _TESTS_DIR.parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from entities import EventLog, SyslogMsg  # noqa: E402
from parse import Parser  # noqa: E402
from tests.fixtures.parser_messages import (  # noqa: E402
    INJECTION_MESSAGES,
    LINUX_SSH_FAILURE,
    LINUX_SSH_FAILURE_TEST_MODE,
    LINUX_SSH_SUCCESS,
    LINUX_SSH_SUCCESS_TEST_MODE,
    MALFORMED_MESSAGES,
    WINDOWS_AUDIT_SUCCESS,
)

_TEST_SUCCESS_PATTERN = (
    r"Accepted\s+publickey\s+for\s+([0-9a-zA-Z_-]+)\s+from\s+"
    r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+port\s+(\d{1,4})+\s+ssh2+\s+"
    r"DATE_TIME\s+(\d{1,4}-\d{1,2}-\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+HOST\s+([\w\+%\-& ]+)"
)
_TEST_FAILURE_PATTERN = (
    r"pam_unix\(sshd:auth\):\s+authentication\s+failure\;\s+login=\s+uid=0\s+"
    r"euid=0\s+tty=ssh+\s+ruser=+\s+rhost=(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+"
    r"user=([0-9a-zA-Z_-]+)\s+DATE_TIME\s+(\d{1,4}-\d{1,2}-\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"HOST\s+([\w\+%\-& ]+)"
)


@pytest.fixture
def parser() -> Parser:
    return Parser(validate_fields=True)


@pytest.fixture
def test_mode_parser() -> Parser:
    return Parser(
        success_pattern=_TEST_SUCCESS_PATTERN,
        failure_pattern=_TEST_FAILURE_PATTERN,
        test_enabled=True,
        validate_fields=True,
    )


def test_linux_ssh_success_field_assertions(parser: Parser) -> None:
    message = SyslogMsg(LINUX_SSH_SUCCESS, "127.0.0.1")
    event = parser.parse_log_line(message)
    assert event is not None
    assert event.username == "alice"
    assert event.ip_address == "10.42.10.2"
    assert event.success is True
    assert isinstance(event.date, datetime)


def test_linux_ssh_failure_field_assertions(parser: Parser) -> None:
    message = SyslogMsg(LINUX_SSH_FAILURE, "127.0.0.1")
    event = parser.parse_log_line(message)
    assert event is not None
    assert event.username == "bob"
    assert event.ip_address == "10.42.10.22"
    assert event.success is False


def test_linux_ssh_success_test_mode_field_assertions(test_mode_parser: Parser) -> None:
    message = SyslogMsg(LINUX_SSH_SUCCESS_TEST_MODE, "127.0.0.1")
    event = test_mode_parser.parse_log_line(message)
    assert event is not None
    assert event.username == "kantselovich"
    assert event.ip_address == "10.42.10.2"
    assert event.server == "ae1-app80-prd"
    assert event.date == datetime(2013, 9, 23, 11, 16, 48)
    assert event.success is True


def test_linux_ssh_failure_test_mode_field_assertions(test_mode_parser: Parser) -> None:
    message = SyslogMsg(LINUX_SSH_FAILURE_TEST_MODE, "127.0.0.1")
    event = test_mode_parser.parse_log_line(message)
    assert event is not None
    assert event.username == "dchiu"
    assert event.ip_address == "10.42.28.46"
    assert event.server == "ae1-app80-prd"
    assert event.date == datetime(2013, 9, 23, 11, 52, 30)
    assert event.success is False


def test_windows_audit_log_field_assertions(parser: Parser) -> None:
    message = SyslogMsg(WINDOWS_AUDIT_SUCCESS, "127.0.0.1")
    event = parser.parse_log_line(message)
    assert event is not None
    assert event.username == "developer"
    assert event.ip_address == "127.0.0.1"
    assert event.server == "USERNAME-DEV-VM"
    assert event.success is True
    assert event.date == datetime(2013, 10, 10, 14, 26, 9)


@pytest.mark.parametrize("payload", MALFORMED_MESSAGES)
def test_malformed_messages_return_none_without_exception(
    parser: Parser, payload: str
) -> None:
    message = SyslogMsg(payload, "127.0.0.1")
    assert parser.parse_log_line(message) is None


def test_oversized_message_does_not_raise(parser: Parser) -> None:
    oversized = "<14>sshd[3070]: Accepted publickey for alice from 10.42.10.2 port 2005 ssh2"
    oversized = oversized + (" " + "A" * 2500)
    message = SyslogMsg(oversized, "127.0.0.1")
    assert len(message.data) > 2048
    event = parser.parse_log_line(message)
    assert event is None or isinstance(event, EventLog)


@pytest.mark.parametrize("payload", INJECTION_MESSAGES.values())
def test_injection_attempts_are_rejected(parser: Parser, payload: str) -> None:
    message = SyslogMsg(payload, "127.0.0.1")
    assert parser.parse_log_line(message) is None


def test_none_message_returns_none(parser: Parser) -> None:
    assert parser.parse_log_line(None) is None


def test_validation_can_be_disabled_for_legacy_behavior() -> None:
    parser = Parser(validate_fields=False)
    message = SyslogMsg(INJECTION_MESSAGES["invalid_ip_after_parse"], "127.0.0.1")
    event = parser.parse_log_line(message)
    assert isinstance(event, EventLog)
    assert event.ip_address == "999.999.999.999"
