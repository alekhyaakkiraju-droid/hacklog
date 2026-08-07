"""Syslog message parser for SSH authentication events."""

import re
from datetime import datetime

from entities import EventLog, SyslogMsg

try:
    from hacklog.validators import validate_parsed_fields
except ImportError:
    from validators import validate_parsed_fields


class Parser:
    def __init__(
        self,
        success_pattern: str | None = None,
        failure_pattern: str | None = None,
        test_enabled: bool = False,
        validate_fields: bool = True,
    ) -> None:
        self.test_enabled = test_enabled
        self.validate_fields = validate_fields
        self.success_pattern = (
            success_pattern
            or r"Accepted\s+publickey\s+for\s+([0-9a-zA-Z_-]+)\s+from\s+"
            r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+port"
        )
        self.failure_pattern = (
            failure_pattern
            or r"pam_unix\(sshd:auth\):\s+authentication\s+failure\;\s+login=\s+uid=0\s+"
            r"euid=0\s+tty=ssh+\s+ruser=+\s+rhost=(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+"
            r"user=([0-9a-zA-Z_-]+)"
        )

    def parse_log_line(self, message: SyslogMsg | None) -> EventLog | None:
        return_event: EventLog | None | bool = False
        if message:
            line = message.data
            host = message.host
            logline = re.sub(r"\s{2,}", " ", line)
            if "Source Network Address" not in line and "Account Name:" not in line:
                logline_parts = logline.split(" ")
                if len(logline_parts) > 5:
                    logline_parts.pop(0)
                    log_entry = " ".join(logline_parts)
                    match = re.match(self.success_pattern, log_entry)
                    if match:
                        user_name = match.groups(0)[0]
                        user_ip = match.groups(0)[1]
                        date_time = datetime.now()

                        if self.test_enabled:
                            date_time = match.groups(0)[3]
                            date_time = datetime.strptime(
                                date_time, "%Y-%m-%d %H:%M:%S"
                            )
                            host = match.groups(0)[4]

                        return_event = EventLog(
                            date_time, user_name, user_ip, True, host
                        )

                    match = re.match(self.failure_pattern, log_entry)
                    if match:
                        user_name = match.groups(0)[1]
                        user_ip = match.groups(0)[0]
                        date_time = datetime.now()

                        if self.test_enabled:
                            date_time = match.groups(0)[2]
                            date_time = datetime.strptime(
                                date_time, "%Y-%m-%d %H:%M:%S"
                            )
                            host = match.groups(0)[3]

                        return_event = EventLog(
                            date_time, user_name, user_ip, False, host
                        )
            elif "Source Network Address" in line and "Account Name:" in line:
                log_data = logline

                log_data = log_data.split(" ")
                more_data = log_data.pop(0)
                more_data = more_data.split(">")
                more_data[1].lstrip()
                day = log_data.pop(0)
                year = "2013"
                time_format = log_data.pop(0)
                host = log_data.pop(0)
                date_time = year + "-" + "10" + "-" + day + " " + time_format
                date_time = datetime.strptime(date_time, "%Y-%m-%d %H:%M:%S")

                user_ip_part = logline.split("Source Network Address:")
                user_ip_part = user_ip_part[1].lstrip()
                user_ip = user_ip_part[0 : user_ip_part.index(" ")].rstrip()

                account_name = logline.split("Account Name:")
                if logline.count("Account Name:") > 1:
                    account_name = account_name[2]
                else:
                    account_name = account_name[1]
                user_name_part = account_name.lstrip()
                user_name = user_name_part[0 : user_name_part.index(" ")].rstrip()
                return_event = EventLog(date_time, user_name, user_ip, True, host)
            else:
                return_event = False
        else:
            return_event = False

        if return_event:
            if self.validate_fields and not validate_parsed_fields(
                return_event.username,
                return_event.ip_address,
                return_event.server,
            ):
                return None
            return return_event
        return None
