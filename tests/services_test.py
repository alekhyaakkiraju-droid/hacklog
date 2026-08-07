import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

_TESTS_DIR = Path(__file__).resolve().parent
_HACKLOG_DIR = _TESTS_DIR.parent / "hacklog"
for _path in (_TESTS_DIR, _HACKLOG_DIR, _TESTS_DIR.parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

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


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self._eventLog = EventLog(datetime.now(), "nrhine", "1.2.3.4", True, "prod")
        self._user = User("nrhine", datetime.now(), 10)
        self._day = Days(datetime.now(), "nrhine", {"1.2.3.5": 1}, 1)
        self._hour = Hours(datetime.now(), "nrhine", {}, 0)
        self._server = Servers(datetime.now(), "nrhine", {}, 0)
        self._ipAddr = IpAddress(datetime.now(), "nrhine", {}, 0)
        updateService._genericDao = MagicMock()
        updateService._userDao = MagicMock()
        updateService._daysDao = MagicMock()
        updateService._hoursDao = MagicMock()
        updateService._serverDao = MagicMock()
        updateService._ipAddressDao = MagicMock()
        emailService.mailServer = MagicMock()

    def test_email_send(self):
        emailService.sendEmailAlert(self._user, self._eventLog)
        emailService.mailServer.connect.assert_called_once()
        emailService.mailServer.sendmail.assert_called_once()

    def test_update_day_new_user(self):
        updateService._daysDao.getProfileByUser.return_value = None
        freq = updateService.updateAndReturnDayFreqForUser(self._eventLog)
        self.assertIsInstance(freq, float)

    def test_update_day_old_user(self):
        updateService._daysDao.getProfileByUser.return_value = self._day
        freq = updateService.updateAndReturnDayFreqForUser(self._eventLog)
        self.assertIsInstance(freq, float)

    def test_update_hour_new_user(self):
        updateService._hoursDao.getProfileByUser.return_value = None
        freq = updateService.updateAndReturnHourFreqForUser(self._eventLog)
        self.assertIsInstance(freq, float)

    def test_update_hour_old_user(self):
        updateService._hoursDao.getProfileByUser.return_value = self._hour
        freq = updateService.updateAndReturnHourFreqForUser(self._eventLog)
        self.assertIsInstance(freq, float)

    def test_update_server_new_user(self):
        updateService._serverDao.getProfileByUser.return_value = None
        freq = updateService.updateAndReturnServerFreqForUser(self._eventLog)
        self.assertIsInstance(freq, float)

    def test_update_server_old_user(self):
        updateService._serverDao.getProfileByUser.return_value = self._server
        freq = updateService.updateAndReturnServerFreqForUser(self._eventLog)
        self.assertIsInstance(freq, float)

    def test_update_ipAddr_new_user(self):
        updateService._ipAddressDao.getProfileByUser.return_value = None
        freq = updateService.updateAndReturnIpFreqForUser(self._eventLog)
        self.assertIsInstance(freq, float)

    def test_update_ipAddr_old_user(self):
        updateService._ipAddressDao.getProfileByUser.return_value = self._ipAddr
        freq = updateService.updateAndReturnIpFreqForUser(self._eventLog)
        self.assertIsInstance(freq, float)

    def test_fetch_user_no_existing(self):
        updateService._userDao.getUserByName.return_value = None
        user = updateService.fetchUser(self._eventLog)
        self.assertIsInstance(user, User)

    def test_fetch_user_existing(self):
        updateService._userDao.getUserByName.return_value = self._user
        user = updateService.fetchUser(self._eventLog)
        self.assertIsInstance(user, User)


def main():
    unittest.main()


if __name__ == "__main__":
    main()
