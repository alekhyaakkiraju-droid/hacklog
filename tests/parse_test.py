import sys
import unittest
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_HACKLOG_DIR = _TESTS_DIR.parent / "hacklog"
for _path in (_TESTS_DIR, _HACKLOG_DIR, _TESTS_DIR.parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from entities import EventLog, SyslogMsg
from parse import Parser
from server import SyslogServer

_server = SyslogServer()
_server.parse_config(str(_TESTS_DIR / "serverTest.conf"))

if _server.test_enabled:
    _success_pattern = (
        r"Accepted\s+publickey\s+for\s+([0-9a-zA-Z_-]+)\s+from\s+"
        r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+port\s+(\d{1,4})+\s+ssh2+\s+"
        r"DATE_TIME\s+(\d{1,4}-\d{1,2}-\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+HOST\s+([\w\+%\-& ]+)"
    )
    _failure_pattern = (
        r"pam_unix\(sshd:auth\):\s+authentication\s+failure\;\s+login=\s+uid=0\s+"
        r"euid=0\s+tty=ssh+\s+ruser=+\s+rhost=(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+"
        r"user=([0-9a-zA-Z_-]+)\s+DATE_TIME\s+(\d{1,4}-\d{1,2}-\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+"
        r"HOST\s+([\w\+%\-& ]+)"
    )
else:
    _success_pattern = None
    _failure_pattern = None

_parser = Parser(_success_pattern, _failure_pattern)


class ParserTests(unittest.TestCase):
    def test_starting_out(self):
        self.assertEqual(1, 1)

    if _server.test_enabled:

        def test_parse_line_success_with_date_ip(self):
            syslog_message = SyslogMsg(
                "<14>sshd[4105]: Accepted publickey for kantselovich from 10.42.10.2 "
                "port 7786 ssh2 DATE_TIME 2013-09-23 11:16:48 HOST ae1-app80-prd",
                "192.168.56.1",
            )
            self.assertIsInstance(_parser.parse_log_line(syslog_message), EventLog)

        def test_parse_line_failure_with_date_ip(self):
            syslog_message = SyslogMsg(
                "<14>sshd[4105]: pam_unix(sshd:auth): authentication failure; login= "
                "uid=0 euid=0 tty=ssh ruser= rhost=10.42.28.46 user=dchiu "
                "DATE_TIME 2013-09-23 11:52:30 HOST ae1-app80-prd",
                "192.168.56.1",
            )
            self.assertIsInstance(_parser.parse_log_line(syslog_message), EventLog)

    else:

        def test_parse_line_success(self):
            syslog_message = SyslogMsg(
                "<14>sshd[3070]: Accepted publickey for kantselovich from 10.42.10.2 "
                "port 2005 ssh2",
                "192.168.56.1",
            )
            self.assertIsInstance(_parser.parse_log_line(syslog_message), EventLog)

        def test_parse_line_failure(self):
            syslog_message = SyslogMsg(
                "<14>sshd[3070]: pam_unix(sshd:auth): authentication failure; login= "
                "uid=0 euid=0 tty=ssh ruser= rhost=10.42.10.22 user=msacks",
                "192.168.56.1",
            )
            self.assertIsInstance(_parser.parse_log_line(syslog_message), EventLog)

        def test_parse_windows_logs(self):
            syslog_message = SyslogMsg(
                "<14>Oct 10 14:26:09 USERNAME-DEV-VM Security-Auditing: 4624: AUDIT_SUCCESS "
                "An account was successfully logged on. Subject: Security ID: S-1-5-18 "
                "Account Name: USERNAME-DEV-VM$ Account Domain: WORKGROUP Logon ID: 0x3e7 "
                "Logon Type: 2 New Logon: Security ID: "
                "S-1-5-21-1223658549-3667468651-3388596622-1001 Account Name: developer "
                "Account Domain: username-dev-vm Logon ID: 0x8b32b5 Logon GUID: "
                "{00000000-0000-0000-0000-000000000000} Process Information: Process ID: "
                "0x820 Process Name: C:\\Windows\\System32\\winlogon.exe Network Information: "
                "Workstation Name: USERNAME-DEV-VM Source Network Address: 127.0.0.1 "
                "Source Port: 0 Detailed Authentication Information: Logon Process: User32 "
                "Authentication Package: Negotiate Transited Services: - Package Name "
                "(NTLM only): - Key Length: 0 This event is generated when a logon session "
                "is created. It is generated on the computer that was accessed. The subject "
                "fields indicate the account on the local system which requested the logon. "
                "This is most commonly a service such as the Server service, or a local "
                "process such as Winlogon.exe or Services.exe. The logon type field "
                "indicates the kind of logon that occurred. The most common types are 2 "
                "(interactive) and 3 (network). The New Logon fields indicate the account "
                "for whom the new logon was created, i.e. the account that was logged on. "
                "The network fields indicate where a remote logon request originated. "
                "Workstation name is not always available and may be left blank in some "
                "cases. The authentication information fields provide detailed information "
                "about this specific logon request. - Logon GUID is a unique identifier "
                "that can be used to correlate this event with a KDC event. - Transited "
                "services indicate which intermediate services have participated in this "
                "logon request. - Package name indicates which sub-protocol was used among "
                "the NTLM protocols. - Key length indicates the length of the generated "
                "session key. This will be 0 if no session key was requested.",
                "192.168.56.1",
            )
            self.assertIsInstance(_parser.parse_log_line(syslog_message), EventLog)


def main():
    unittest.main()


if __name__ == "__main__":
    main()
