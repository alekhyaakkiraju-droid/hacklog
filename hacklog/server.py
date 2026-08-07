"""Hacklog syslog server entrypoint."""

import asyncio
import configparser

from config import load_config_or_exit
from entities import create_db_engine, create_tables
from logging_config import configure_logging, get_logger
from optparse import OptionParser
from parse import Parser
from alerting import AlertService
from scoring import ScoringEngine
from services import UpdateService
from session import Session
from syslog_server import DEFAULT_QUEUE_MAXSIZE, run_async_syslog_server

logger = get_logger("server")


class SyslogServer:
    """Syslog server orchestrating config, parsing, and asyncio UDP ingestion."""

    def __init__(self) -> None:
        self.dbFile = "hacklog.db"
        self.port = 10514
        self.bind_address = "127.0.0.1"
        self.config_file = "../conf/server.conf"
        self.loglevel = 10
        self.usage = "usage: %prog -c config_file"
        self.testEnabled = False
        self.emailTest = False
        self.successPattern: str | None = None
        self.failurePattern: str | None = None
        self.message_queue: asyncio.Queue = asyncio.Queue(maxsize=DEFAULT_QUEUE_MAXSIZE)
        self.scoring_engine: ScoringEngine | None = None
        self.db_engine = None

    def parceConfig(self, config_file: str) -> None:
        config = configparser.ConfigParser(interpolation=None)
        config.read(config_file)

        if config.has_option("SyslogServer", "bind_address"):
            self.bind_address = config.get("SyslogServer", "bind_address")
        if config.has_option("SyslogServer", "bind_port"):
            self.port = config.getint("SyslogServer", "port")
        if config.has_option("SyslogServer", "db_file"):
            self.dbFile = config.get("SyslogServer", "db_file")
        if config.has_option("MailServer", "gmail_test"):
            self.emailTest = config.getboolean("MailServer", "gmail_test")
        if config.has_option("Parse", "test_enabled"):
            self.testEnabled = config.getboolean("Parse", "test_enabled")
        if config.has_option("Parse", "success_pattern"):
            self.successPattern = config.get("Parse", "success_pattern")
        if config.has_option("Parse", "failure_pattern"):
            self.failurePattern = config.get("Parse", "failure_pattern")

    def readCmdArgs(self) -> None:
        cmd_parser = OptionParser(usage=self.usage)
        cmd_parser.add_option(
            "-c",
            "--config",
            dest="config_file",
            help="configuration file",
            metavar="FILE",
        )
        options, _args = cmd_parser.parse_args()
        if options.config_file:
            self.config_file = options.config_file

    def setLogging(self) -> None:
        configure_logging(level=self.loglevel)

    def _build_parser(self) -> Parser:
        if self.testEnabled:
            return Parser(self.successPattern, self.failurePattern, self.testEnabled)
        return Parser()

    def run(self) -> None:
        if self.scoring_engine is None:
            raise RuntimeError("ScoringEngine must be wired before run()")

        app_config = load_config_or_exit()
        syslog = app_config.syslog
        bind_address = self.bind_address or syslog.bind_address
        port = self.port or syslog.port
        parser = self._build_parser()

        asyncio.run(
            run_async_syslog_server(
                bind_address=bind_address,
                port=port,
                parser=parser,
                process_event=self.scoring_engine.processEventLog,
                syslog_config=syslog,
                queue=self.message_queue,
            )
        )

    def start(self) -> None:
        self.readCmdArgs()
        self.parceConfig(self.config_file)
        self.setLogging()
        app_config = load_config_or_exit()
        self.db_engine = create_db_engine(self)
        create_tables(self.db_engine)
        Session.configure(bind=self.db_engine)
        update_service = UpdateService()
        alert_service = AlertService(app_config.smtp)
        self.scoring_engine = ScoringEngine(update_service, alert_service)
        self.run()


def main() -> None:
    server = SyslogServer()
    server.start()


if __name__ == "__main__":
    main()
