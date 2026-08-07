"""CSV replay utility for generating syslog test traffic."""

from __future__ import annotations

import csv
import logging
import logging.handlers
import random
import sys
from datetime import datetime
from pathlib import Path
from time import sleep

try:
    from hacklog.server import SyslogServer
except ImportError:
    from server import SyslogServer

logger = logging.getLogger(__name__)

CSV_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
REQUIRED_CSV_FIELDS = ("Date Time", "User", "IP", "Login_Status", "Server_Name")


def _demo_syslog_pid() -> int:
    """Synthetic syslog PID for CSV replay — not used for security purposes."""
    return random.randrange(1000, 9999, 345)  # NOSONAR


def _demo_syslog_port() -> int:
    """Synthetic syslog port for CSV replay — not used for security purposes."""
    return random.randrange(1021, 9999, 123)  # NOSONAR


def parse_csv_datetime(raw_value: str, *, field_name: str = "Date Time") -> datetime:
    """Parse a CSV date-time field into a timezone-naive datetime."""
    if not isinstance(raw_value, str) or not raw_value.strip():
        msg = (
            f"Invalid {field_name}: expected non-empty string in "
            f"'{CSV_DATETIME_FORMAT}' format, got {raw_value!r}"
        )
        raise ValueError(msg)
    try:
        return datetime.strptime(raw_value.strip(), CSV_DATETIME_FORMAT)
    except ValueError as exc:
        msg = (
            f"Invalid {field_name}: expected format '{CSV_DATETIME_FORMAT}', "
            f"got {raw_value!r}"
        )
        raise ValueError(msg) from exc


def format_syslog_datetime(event_time: datetime) -> str:
    """Format a datetime for DATE_TIME tokens in replayed syslog messages."""
    return event_time.strftime(CSV_DATETIME_FORMAT)


def resolve_csv_input_path(file_name: str, base_dir: Path | None = None) -> Path:
    """Resolve a CSV path and reject traversal outside the base directory."""
    base = (base_dir or Path.cwd()).resolve()
    candidate = Path(file_name)
    if not candidate.is_absolute():
        candidate = base / candidate
    resolved = candidate.resolve()
    if not resolved.is_relative_to(base):
        msg = f"CSV path must stay within {base}: {file_name}"
        raise ValueError(msg)
    if not resolved.is_file():
        raise FileNotFoundError(f"CSV file not found: {resolved}")
    return resolved


def _is_successful_login(login_status: str) -> bool:
    return login_status.strip().upper() == "TRUE"


class ReadCSVFiles:
    def __init__(self, test_enabled: bool = False) -> None:
        self.test_enabled = test_enabled

    def log_messages(self, log_data: dict[str, str]) -> None:
        missing = [field for field in REQUIRED_CSV_FIELDS if field not in log_data]
        if missing:
            missing_fields = ", ".join(missing)
            msg = f"CSV row missing required field(s): {missing_fields}"
            raise ValueError(msg)

        event_time = parse_csv_datetime(log_data["Date Time"])
        date_time_token = format_syslog_datetime(event_time)
        pid = _demo_syslog_pid()
        port = _demo_syslog_port()

        if _is_successful_login(log_data["Login_Status"]):
            if self.test_enabled:
                sys_log_message = (
                    f"sshd[{pid}]: Accepted publickey for {log_data['User']} "
                    f"from {log_data['IP']} port {port} ssh2 "
                    f"DATE_TIME {date_time_token} HOST {log_data['Server_Name']}"
                )
            else:
                sys_log_message = (
                    f"sshd[{pid}]: Accepted publickey for {log_data['User']} "
                    f"from {log_data['IP']} port {port} ssh2"
                )
        elif self.test_enabled:
            sys_log_message = (
                f"sshd[{pid}]: pam_unix(sshd:auth): authentication failure; "
                f"login= uid=0 euid=0 tty=ssh ruser= rhost={log_data['IP']} "
                f"user={log_data['User']} DATE_TIME {date_time_token} "
                f"HOST {log_data['Server_Name']}"
            )
        else:
            sys_log_message = (
                f"sshd[{pid}]: pam_unix(sshd:auth): authentication failure; "
                f"login= uid=0 euid=0 tty=ssh ruser= rhost={log_data['IP']} "
                f"user={log_data['User']}"
            )

        logger.info(sys_log_message)

    def read_line_generate_logs(self, reader: csv.reader) -> None:
        row_num = 0
        headers: list[str] = []
        for row in reader:
            if row_num == 0:
                headers = row
            else:
                each_row_data: dict[str, str] = {}
                for col_num, col in enumerate(row):
                    each_row_data[headers[col_num]] = col
                if row_num % 5 == 0:
                    sleep(50.0 / 1000.0)
                self.log_messages(each_row_data)
            row_num += 1


def main() -> None:
    server = SyslogServer()
    server.parse_config("../conf/server.conf")
    read_csv = ReadCSVFiles(server.test_enabled)

    if len(sys.argv) >= 3:
        file_name = sys.argv[1]
        ip_address = sys.argv[2]
    else:
        file_name = "data"
        ip_address = "127.0.0.1"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    handler = logging.handlers.SysLogHandler(address=(ip_address, 10514))
    root_logger.addHandler(handler)

    csv_path = resolve_csv_input_path(file_name)
    with csv_path.open(encoding="utf-8", newline="") as file_object:
        reader = csv.reader(file_object)
        read_csv.read_line_generate_logs(reader)


if __name__ == "__main__":
    main()
