"""CSV replay utility for generating syslog test traffic."""

import csv
import logging
import logging.handlers
import random
import sys
from datetime import datetime
from time import sleep

from server import SyslogServer

logger = logging.getLogger()


class ReadCSVFiles:
    def __init__(self, testEnabled: bool = False) -> None:
        self.testEnabled = testEnabled

    def logMessages(self, logData: dict[str, str]) -> None:
        sys_log_message = ""
        logData["Date Time"] = datetime.strptime(logData["Date Time"], "%Y-%m-%d %H:%M:%S")
        if self.testEnabled:
            if logData["Login_Status"] == "TRUE" or logData["Login_Status"] == "True":
                sys_log_message = (
                    "sshd[%d]: Accepted publickey for %s from %s port %d ssh2 DATE_TIME %s HOST %s"
                    % (
                        random.randrange(1000, 9999, 345),
                        logData["User"],
                        logData["IP"],
                        random.randrange(1021, 9999, 123),
                        logData["Date Time"],
                        logData["Server_Name"],
                    )
                )
            else:
                sys_log_message = (
                    "sshd[%d]: pam_unix(sshd:auth): authentication failure; login= uid=0 "
                    "euid=0 tty=ssh ruser= rhost=%s user=%s DATE_TIME %s HOST %s"
                    % (
                        random.randrange(1000, 9999, 345),
                        logData["IP"],
                        logData["User"],
                        logData["Date Time"],
                        logData["Server_Name"],
                    )
                )
        else:
            if logData["Login_Status"] == "TRUE" or logData["Login_Status"] == "True":
                sys_log_message = (
                    "sshd[%d]: Accepted publickey for %s from %s port %d ssh2"
                    % (
                        random.randrange(1000, 9999, 345),
                        logData["User"],
                        logData["IP"],
                        random.randrange(1021, 9999, 123),
                    )
                )
            else:
                sys_log_message = (
                    "sshd[%d]: pam_unix(sshd:auth): authentication failure; login= uid=0 "
                    "euid=0 tty=ssh ruser= rhost=%s user=%s"
                    % (
                        random.randrange(1000, 9999, 345),
                        logData["IP"],
                        logData["User"],
                    )
                )

        logger.info(sys_log_message)

    def readLineGenerateLogs(self, reader: csv.reader) -> None:
        row_num = 0
        file_data: list[str] = []
        for row in reader:
            each_row_data: dict[str, str] = {}
            if row_num == 0:
                file_data = row
            else:
                col_num = 0
                for col in row:
                    each_row_data[file_data[col_num]] = col
                    col_num += 1
                if row_num % 5 == 0:
                    sleep(50.0 / 1000.0)
                self.logMessages(each_row_data)
            row_num += 1


def main() -> None:
    server = SyslogServer()
    server.parceConfig("../conf/server.conf")
    if server.testEnabled:
        read_csv = ReadCSVFiles(server.testEnabled)
    else:
        read_csv = ReadCSVFiles()

    if len(sys.argv) >= 3:
        file_name = sys.argv[1]
        ip_address = sys.argv[2]
    else:
        file_name = "data"
        ip_address = "127.0.0.1"

    global logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    handler = logging.handlers.SysLogHandler(address=(ip_address, 10514))
    logger.addHandler(handler)

    with open(file_name, encoding="utf-8", newline="") as file_object:
        reader = csv.reader(file_object)
        read_csv.readLineGenerateLogs(reader)


if __name__ == "__main__":
    main()
