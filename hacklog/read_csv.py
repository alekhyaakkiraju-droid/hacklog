"""CSV replay utility for generating syslog test traffic.

CSV rows are replayed as syslog messages for integration testing. Date-time
fields must match ``HACKLOG_CSV_DATETIME_FORMAT`` (default ``%Y-%m-%d %H:%M:%S``).
Malformed rows are logged and skipped during batch replay.
"""

from __future__ import annotations

import csv
import logging
import logging.handlers
import os
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

DEFAULT_CSV_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
CSV_DATETIME_FORMAT = DEFAULT_CSV_DATETIME_FORMAT
CSV_DATETIME_FORMAT_ENV = "HACKLOG_CSV_DATETIME_FORMAT"
REQUIRED_CSV_FIELDS = ("Date Time", "User", "IP", "Login_Status", "Server_Name")


def get_csv_datetime_format() -> str:
    """Return the strptime/strftime pattern for CSV date-time fields."""
    return os.environ.get(CSV_DATETIME_FORMAT_ENV, DEFAULT_CSV_DATETIME_FORMAT)


def _demo_syslog_pid() -> int:
    """Synthetic syslog PID for CSV replay — not used for security purposes."""
    return random.randrange(1000, 9999, 345)  # NOSONAR


def _demo_syslog_port() -> int:
    """Synthetic syslog port for CSV replay — not used for security purposes."""
    return random.randrange(1021, 9999, 123)  # NOSONAR


def parse_csv_datetime(
    raw_value: str | None,
    *,
    field_name: str = "Date Time",
) -> datetime:
    """Parse a CSV date-time field into a timezone-naive datetime."""
    date_format = get_csv_datetime_format()
    if raw_value is None:
        msg = f"Invalid {field_name}: value cannot be None"
        logger.error(msg)
        raise ValueError(msg)
    if not isinstance(raw_value, str) or not raw_value.strip():
        msg = (
            f"Invalid {field_name}: expected non-empty string in "
            f"'{date_format}' format, got {raw_value!r}"
        )
        logger.error(msg)
        raise ValueError(msg)
    try:
        return datetime.strptime(raw_value.strip(), date_format)
    except ValueError as exc:
        msg = (
            f"Invalid {field_name}: expected format '{date_format}', "
            f"got {raw_value!r}"
        )
        logger.error(msg)
        raise ValueError(msg) from exc


def format_syslog_datetime(event_time: datetime) -> str:
    """Format a datetime for DATE_TIME tokens in replayed syslog messages."""
    return event_time.strftime(get_csv_datetime_format())


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
                try:
                    self.log_messages(each_row_data)
                except ValueError as exc:
                    logger.error("Skipping CSV row %d: %s", row_num + 1, exc)
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
