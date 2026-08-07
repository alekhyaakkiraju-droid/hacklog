import sys
import time
import thread
import random
import algorithm
import signal

from twisted.internet.protocol import DatagramProtocol
from twisted.internet import reactor, defer

from optparse import OptionParser
from ConfigParser import ConfigParser
from parse import Parser
from entities import SyslogMsg
from Queue import Queue
from entities import create_tables, create_db_engine
from config import load_config_or_exit
from logging_config import configure_logging, get_logger

queue = Queue()
logger = get_logger("server")

class SyslogServer():
    """
    Syslog server based on twisted library
    """
    def __init__(self):
      self.dbFile = 'hacklog.db'
      self.port = 10514
      self.bind_address = '127.0.0.1'
      self.config_file = '../conf/server.conf'
      self.loglevel = 10
      self.running = True
      self.usage = "usage: %prog -c config_file"
      self.testEnabled = False
      self.emailTest = False
      self.successPattern = None
      self.failurePattern = None
     
    def parceConfig(self, config_file):
       config = ConfigParser()
       config.read(config_file)
        
       if config.has_option('SyslogServer', 'bind_address'):
         self.bind_address = config.get('SyslogServer', 'bind_address')
       if config.has_option('SyslogServer', 'bind_port'):
         self.port = config.getint('SyslogServer', 'port')       
       if config.has_option('SyslogServer', 'db_file'):
         self.dfFile = config.get('SyslogServer', 'df_file')
       if config.has_option('MailServer', 'gmail_test'):
         self.emailTest = config.getboolean('MailServer', 'gmail_test')
       if config.has_option('Parse', 'test_enabled'):
         self.testEnabled = config.getboolean('Parse', 'test_enabled')
       if config.has_option('Parse', 'success_pattern'):
         self.successPattern = config.get('Parse', 'success_pattern')
       if config.has_option('Parse', 'failure_pattern'):
         self.failurePattern = config.get('Parse', 'failure_pattern')

    def readCmdArgs(self):
      cmdParser = OptionParser(usage=self.usage)
      cmdParser.add_option("-c", "--config", dest="config_file",
                      help="configuration file", metavar="FILE")
      (options, args) = cmdParser.parse_args()
      if options.config_file:
        self.config_file = options.config_file

    def setLogging(self):
      configure_logging(level=self.loglevel)

    
    def interrupt(self, signum, stackframe):
      logger.debug("signal_received", operation="handle_signal", signal=signum)
      self.running = False
      queue.put(SyslogMsg())
      self.stop()
 
    def messageParcer(self):
       logger.debug("parser_thread_started", operation="message_parser_start", thread_id=thread.get_ident())
       parser = None
       # get parsing patterns from config file when in testing mode
       if self.testEnabled:
         parser = Parser(self.successPattern, self.failurePattern, self.testEnabled)
       else:
         parser = Parser()

       while self.running:
            msg = queue.get()
            eventLog = parser.parseLogLine(msg)
            if eventLog:
                algorithm.processEventLog(eventLog)
                logger.debug(
                    "message_processed",
                    operation="process_message",
                    queue_size=queue.qsize(),
                    source_host=msg.host,
                    source_port=msg.port,
                )
 
    def cleanupThread(self):
      threadPool = reactor.getThreadPool()
      threadPool.stop()

    def run(self):
      signal.signal(signal.SIGINT, self.interrupt)
      reactor.callInThread(self.messageParcer)
      reactor.listenUDP(self.port, SyslogReader())
      reactor.run()

    def start(self):
      self.readCmdArgs()
      self.parceConfig(self.config_file)
      self.setLogging()
      app_config = load_config_or_exit()
      algorithm.setServices(app_config.smtp)
      create_db_engine(self)
      create_tables()
      self.run() 

    def stop(self):
      reactor.stop()


class SyslogReader(DatagramProtocol):

    def datagramReceived(self, data, (host, port)):
        logger.info(
            "message_received",
            operation="receive_datagram",
            source_ip=host,
            source_port=port,
            message_size=len(data),
        )
        syslogMsg = SyslogMsg(data, host, port)
        queue.put(syslogMsg)

def main():

    server = SyslogServer()
    server.start()

if __name__ == '__main__':
    main()
