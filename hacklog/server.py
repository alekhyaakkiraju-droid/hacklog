"""Twisted-based syslog UDP server."""

import configparser
import queue
import signal
import threading

import algorithm
from config import load_config_or_exit
from entities import SyslogMsg, create_db_engine, create_tables
from logging_config import configure_logging, get_logger
from optparse import OptionParser
from parse import Parser
from twisted.internet import reactor
from twisted.internet.protocol import DatagramProtocol

message_queue: queue.Queue[SyslogMsg] = queue.Queue()
logger = get_logger("server")


class SyslogServer:
    """Syslog server based on twisted library."""

    def __init__(self) -> None:
        self.dbFile = "hacklog.db"
        self.port = 10514
        self.bind_address = "127.0.0.1"
        self.config_file = "../conf/server.conf"
        self.loglevel = 10
        self.running = True
        self.usage = "usage: %prog -c config_file"
        self.testEnabled = False
        self.emailTest = False
        self.successPattern: str | None = None
        self.failurePattern: str | None = None

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

    def interrupt(self, signum: int, stackframe: object) -> None:
        logger.debug("signal_received", operation="handle_signal", signal=signum)
        self.running = False
        message_queue.put(SyslogMsg())
        self.stop()

    def messageParcer(self) -> None:
        logger.debug(
            "parser_thread_started",
            operation="message_parser_start",
            thread_id=threading.get_ident(),
        )
        if self.testEnabled:
            parser = Parser(self.successPattern, self.failurePattern, self.testEnabled)
        else:
            parser = Parser()

        while self.running:
            msg = message_queue.get()
            event_log = parser.parseLogLine(msg)
            if event_log:
                algorithm.processEventLog(event_log)
                logger.debug(
                    "message_processed",
                    operation="process_message",
                    queue_size=message_queue.qsize(),
                    source_host=msg.host,
                    source_port=msg.port,
                )

    def cleanupThread(self) -> None:
        thread_pool = reactor.getThreadPool()
        thread_pool.stop()

    def run(self) -> None:
        signal.signal(signal.SIGINT, self.interrupt)
        reactor.callInThread(self.messageParcer)
        reactor.listenUDP(self.port, SyslogReader())
        reactor.run()

    def start(self) -> None:
        self.readCmdArgs()
        self.parceConfig(self.config_file)
        self.setLogging()
        app_config = load_config_or_exit()
        algorithm.setServices(app_config.smtp)
        create_db_engine(self)
        create_tables()
        self.run()

    def stop(self) -> None:
        reactor.stop()


class SyslogReader(DatagramProtocol):
    def datagramReceived(self, data: bytes, addr: tuple[str, int]) -> None:
        host, port = addr
        text = data.decode("utf-8", errors="replace")
        logger.info(
            "message_received",
            operation="receive_datagram",
            source_ip=host,
            source_port=port,
            message_size=len(data),
        )
        syslog_msg = SyslogMsg(text, host, port)
        message_queue.put(syslog_msg)


def main() -> None:
    server = SyslogServer()
    server.start()


if __name__ == "__main__":
    main()
