"""WO-041: Parser accepts SyslogMsg entities instead of raw log strings."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_HACKLOG_DIR = _TESTS_DIR.parent / "hacklog"
for _path in (_HACKLOG_DIR, _TESTS_DIR.parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from entities import EventLog, SyslogMsg  # noqa: E402
from parse import Parser  # noqa: E402

SUCCESS_LINE = (
    "<14>sshd[3070]: Accepted publickey for alice from 10.42.10.2 port 2005 ssh2"
)
FAILURE_LINE = (
    "<14>sshd[3070]: pam_unix(sshd:auth): authentication failure; login= "
    "uid=0 euid=0 tty=ssh ruser= rhost=10.42.10.22 user=bob"
)


@pytest.fixture
def parser() -> Parser:
    return Parser(validate_fields=True)


def test_parse_log_line_accepts_syslog_msg_entity(parser: Parser) -> None:
    message = SyslogMsg(SUCCESS_LINE, "relay-host.internal", 514)
    event = parser.parse_log_line(message)
    assert isinstance(event, EventLog)


def test_parse_log_line_uses_syslog_msg_host_for_server(parser: Parser) -> None:
    relay_host = "syslog-relay.example.com"
    message = SyslogMsg(SUCCESS_LINE, relay_host, 514)
    event = parser.parse_log_line(message)
    assert event is not None
    assert event.server == relay_host
    assert relay_host not in SUCCESS_LINE


def test_parse_log_line_reads_payload_from_syslog_msg_data(parser: Parser) -> None:
    message = SyslogMsg(SUCCESS_LINE, "prod-web-01", 514)
    event = parser.parse_log_line(message)
    assert event is not None
    assert event.username == "alice"
    assert event.ip_address == "10.42.10.2"
    assert event.success is True


def test_parse_log_line_failure_pattern_uses_syslog_msg_host(parser: Parser) -> None:
    relay_host = "edge-collector.internal"
    message = SyslogMsg(FAILURE_LINE, relay_host, 514)
    event = parser.parse_log_line(message)
    assert event is not None
    assert event.username == "bob"
    assert event.ip_address == "10.42.10.22"
    assert event.success is False
    assert event.server == relay_host


def test_parse_log_line_returns_none_for_none_message(parser: Parser) -> None:
    assert parser.parse_log_line(None) is None


def test_parse_log_line_distinguishes_host_from_data_prefix(parser: Parser) -> None:
    """Host must not be taken from the first token of SyslogMsg.data."""
    data_with_hostlike_prefix = (
        "192.168.56.1 <14>sshd[3070]: Accepted publickey for carol "
        "from 10.42.10.2 port 2005 ssh2"
    )
    message = SyslogMsg(data_with_hostlike_prefix, "actual-relay", 514)
    event = parser.parse_log_line(message)
    assert event is not None
    assert event.server == "actual-relay"
    assert event.username == "carol"
