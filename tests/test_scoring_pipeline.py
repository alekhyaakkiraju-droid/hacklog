"""Integration test: syslog parse → score pipeline with injected dependencies."""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

_TESTS_DIR = Path(__file__).resolve().parent
_HACKLOG_DIR = _TESTS_DIR.parent / "hacklog"
for _path in (_HACKLOG_DIR, _TESTS_DIR.parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from entities import EventLog, SyslogMsg, User  # noqa: E402
from parse import Parser  # noqa: E402
from scoring import ScoringEngine  # noqa: E402


def test_pipeline_parse_to_score_with_injected_mocks() -> None:
    syslog_line = (
        "<14>sshd[3070]: Accepted publickey for nrhine from 10.42.10.2 port 2005 ssh2"
    )
    parser = Parser()
    syslog_msg = SyslogMsg(syslog_line, "127.0.0.1", 514)
    event_log = parser.parse_log_line(syslog_msg)
    assert isinstance(event_log, EventLog)

    update_service = MagicMock()
    alert_service = MagicMock()
    user = User("nrhine", datetime.now(), 0)
    update_service.fetch_user.return_value = user
    update_service.update_and_return_hour_freq_for_user.return_value = 0.25
    update_service.update_and_return_day_freq_for_user.return_value = 0.25
    update_service.update_and_return_server_freq_for_user.return_value = 0.25
    update_service.update_and_return_ip_freq_for_user.return_value = 0.25

    engine = ScoringEngine(update_service, alert_service)
    engine.process_event_log(event_log)

    update_service.audit_event_log.assert_called_once_with(event_log)
    update_service.update_user_score.assert_called_once()
    alert_service.send_email_alert.assert_not_called()
