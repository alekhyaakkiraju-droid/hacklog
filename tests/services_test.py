import sys
import unittest
from datetime import datetime
from pathlib import Path

import pytest

pytest.importorskip("mockito")
from mockito import any, mock, verify, when

_TESTS_DIR = Path(__file__).resolve().parent
_HACKLOG_DIR = _TESTS_DIR.parent / "hacklog"
for _path in (_TESTS_DIR, _HACKLOG_DIR, _TESTS_DIR.parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from compat import _Compat
from entities import Days, EventLog, Hours, IpAddress, Servers, User
from services import EmailService, UpdateService

try:
    from hacklog.config import SmtpConfig
except ImportError:
    from config import SmtpConfig

from pydantic import SecretStr

_smtp_config = SmtpConfig(
    host="smtp.example.com",
    port=587,
    username="test@example.com",
    password=SecretStr("test-password"),
    sender="alerts@example.com",
    recipient="soc@example.com",
    use_tls=True,
)
emailService = EmailService(_smtp_config)
updateService = UpdateService()


class ServiceTests(unittest.TestCase, _Compat):
    def setUp(self):
        self._eventLog = EventLog(datetime.now(), "nrhine", "1.2.3.4", True, "prod")
        self._user = User("nrhine", datetime.now(), 10)
        self._day = Days(datetime.now(), "nrhine", {"1.2.3.5": 1}, 1)
        self._hour = Hours(datetime.now(), "nrhine", {}, 0)
        self._server = Servers(datetime.now(), "nrhine", {}, 0)
        self._ipAddr = IpAddress(datetime.now(), "nrhine", {}, 0)
        updateService._genericDao = mock()
        updateService._userDao = mock()
        updateService._daysDao = mock()
        updateService._hoursDao = mock()
        updateService._serverDao = mock()
        updateService._ipAddressDao = mock()
        emailService.mailServer = mock()

    def test_email_send(self):
        when(emailService.mailServer).connect().thenReturn(True)
        when(emailService.mailServer).sendmail().thenReturn(True)
        emailService.sendEmailAlert(self._user, self._eventLog)
        verify(emailService.mailServer, times=1).sendmail(any(), any(), any())

    def test_update_day_new_user(self):
        when(updateService._daysDao).getProfileByUser(self._eventLog.username).thenReturn(None)
        freq = updateService.updateAndReturnDayFreqForUser(self._eventLog)
        self.assertIsInstance(freq, float)

    def test_update_day_old_user(self):
        when(updateService._daysDao).getProfileByUser(self._eventLog.username).thenReturn(self._day)
        freq = updateService.updateAndReturnDayFreqForUser(self._eventLog)
        self.assertIsInstance(freq, float)

    def test_update_hour_new_user(self):
        when(updateService._hoursDao).getProfileByUser(self._eventLog.username).thenReturn(None)
        freq = updateService.updateAndReturnHourFreqForUser(self._eventLog)
        self.assertIsInstance(freq, float)

    def test_update_hour_old_user(self):
        when(updateService._hoursDao).getProfileByUser(self._eventLog.username).thenReturn(self._hour)
        freq = updateService.updateAndReturnHourFreqForUser(self._eventLog)
        self.assertIsInstance(freq, float)

    def test_update_server_new_user(self):
        when(updateService._serverDao).getProfileByUser(self._eventLog.username).thenReturn(None)
        freq = updateService.updateAndReturnServerFreqForUser(self._eventLog)
        self.assertIsInstance(freq, float)

    def test_update_server_old_user(self):
        when(updateService._serverDao).getProfileByUser(self._eventLog.username).thenReturn(
            self._server
        )
        freq = updateService.updateAndReturnServerFreqForUser(self._eventLog)
        self.assertIsInstance(freq, float)

    def test_update_ipAddr_new_user(self):
        when(updateService._ipAddressDao).getProfileByUser(self._eventLog.username).thenReturn(None)
        freq = updateService.updateAndReturnIpFreqForUser(self._eventLog)
        self.assertIsInstance(freq, float)

    def test_update_ipAddr_old_user(self):
        when(updateService._ipAddressDao).getProfileByUser(self._eventLog.username).thenReturn(
            self._ipAddr
        )
        freq = updateService.updateAndReturnIpFreqForUser(self._eventLog)
        self.assertIsInstance(freq, float)

    def test_fetch_user_no_existing(self):
        when(updateService._userDao).getUserByName(self._eventLog.username).thenReturn(None)
        user = updateService.fetchUser(self._eventLog)
        self.assertIsInstance(user, User)

    def test_fetch_user_existing(self):
        when(updateService._userDao).getUserByName(self._eventLog.username).thenReturn(self._user)
        user = updateService.fetchUser(self._eventLog)
        self.assertIsInstance(user, User)


def main():
    unittest.main()


if __name__ == "__main__":
    main()
