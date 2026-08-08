"""Hacklog syslog server entrypoint."""

import asyncio
import configparser
from optparse import OptionParser

from alerting import AlertService
from config import load_config_or_exit
from entities import create_db_engine, create_tables
from logging_config import configure_logging, get_logger
from parse import Parser
from scoring import ScoringEngine
from services import UpdateService
from session import Session
from syslog_server import DEFAULT_QUEUE_MAXSIZE, run_async_syslog_server

logger = get_logger("server")


class SyslogServer:
    """Syslog server orchestrating config, parsing, and asyncio UDP ingestion."""

    def __init__(self) -> None:
        self.db_file = "hacklog.db"
        self.port: int | None = None
        self.bind_address: str | None = None
        self.config_file = "../conf/server.conf"
        self.loglevel = 10
        self.usage = "usage: %prog -c config_file"
        self.test_enabled = False
        self.email_test = False
        self.success_pattern: str | None = None
        self.failure_pattern: str | None = None
        self.message_queue: asyncio.Queue = asyncio.Queue(maxsize=DEFAULT_QUEUE_MAXSIZE)
        self.scoring_engine: ScoringEngine | None = None
        self.db_engine = None

    def parse_config(self, config_file: str) -> None:
        config = configparser.ConfigParser(interpolation=None)
        config.read(config_file)

        if config.has_option("SyslogServer", "bind_address"):
            self.bind_address = config.get("SyslogServer", "bind_address")
        if config.has_option("SyslogServer", "bind_port"):
            self.port = config.getint("SyslogServer", "port")
        if config.has_option("SyslogServer", "db_file"):
            self.db_file = config.get("SyslogServer", "db_file")
        if config.has_option("MailServer", "gmail_test"):
            self.email_test = config.getboolean("MailServer", "gmail_test")
        if config.has_option("Parse", "test_enabled"):
            self.test_enabled = config.getboolean("Parse", "test_enabled")
        if config.has_option("Parse", "success_pattern"):
            self.success_pattern = config.get("Parse", "success_pattern")
        if config.has_option("Parse", "failure_pattern"):
            self.failure_pattern = config.get("Parse", "failure_pattern")

    def read_cmd_args(self) -> None:
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

    def set_logging(self) -> None:
        configure_logging(level=self.loglevel)

    def _build_parser(self) -> Parser:
        if self.test_enabled:
            return Parser(self.success_pattern, self.failure_pattern, self.test_enabled)
        return Parser()

    def _release_resources(self) -> None:
        if self.db_engine is not None:
            self.db_engine.dispose()
            self.db_engine = None
        logger.info("server_resources_released", operation="shutdown")

    def run(self) -> None:
        if self.scoring_engine is None:
            raise RuntimeError("ScoringEngine must be wired before run()")

        app_config = load_config_or_exit()
        syslog = app_config.syslog
        bind_address = self.bind_address or syslog.bind_address
        port = self.port or syslog.port
        parser = self._build_parser()

        try:
            asyncio.run(
                run_async_syslog_server(
                    bind_address=bind_address,
                    port=port,
                    parser=parser,
                    process_event=self.scoring_engine.process_event_log,
                    syslog_config=syslog,
                    queue=self.message_queue,
                    on_shutdown=self._release_resources,
                )
            )
        finally:
            self._release_resources()

    def start(self) -> None:
        self.read_cmd_args()
        self.parse_config(self.config_file)
        self.set_logging()
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
