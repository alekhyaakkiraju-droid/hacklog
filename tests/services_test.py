import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

_TESTS_DIR = Path(__file__).resolve().parent
_HACKLOG_DIR = _TESTS_DIR.parent / "hacklog"
for _path in (_TESTS_DIR, _HACKLOG_DIR, _TESTS_DIR.parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from alerting import AlertService
from entities import EventLog, Profile, ProfileType, User
from services import UpdateService

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
email_service = AlertService(_smtp_config)
update_service = UpdateService()

class ServiceTests(unittest.TestCase):
    def setUp(self):
        self._event_log = EventLog(datetime.now(), "nrhine", "1.2.3.4", True, "prod")
        self._user = User("nrhine", datetime.now(), 10)
        self._day = Profile(datetime.now(), "nrhine", ProfileType.DAYS, {"1.2.3.5": 1}, 1)
        self._hour = Profile(datetime.now(), "nrhine", ProfileType.HOURS, {}, 0)
        self._server = Profile(datetime.now(), "nrhine", ProfileType.SERVER, {}, 0)
        self._ip_addr = Profile(
            datetime.now(), "nrhine", ProfileType.IP_ADDRESS, {}, 0
        )
        update_service._profile_repository = MagicMock()
        update_service._user_repository = MagicMock()
        update_service._audit_repository = MagicMock()
        self._smtp_sender = AsyncMock()
        email_service._smtp_sender = self._smtp_sender

    def test_email_send(self):
        email_service.send_email_alert(self._user, self._event_log)
        self._smtp_sender.assert_awaited_once()

    def test_update_day_new_user(self):
        update_service._profile_repository.get_profile.return_value = None
        freq = update_service.update_and_return_day_freq_for_user(self._event_log)
        self.assertIsInstance(freq, float)

    def test_update_day_old_user(self):
        update_service._profile_repository.get_profile.return_value = self._day
        freq = update_service.update_and_return_day_freq_for_user(self._event_log)
        self.assertIsInstance(freq, float)

    def test_update_hour_new_user(self):
        update_service._profile_repository.get_profile.return_value = None
        freq = update_service.update_and_return_hour_freq_for_user(self._event_log)
        self.assertIsInstance(freq, float)

    def test_update_hour_old_user(self):
        update_service._profile_repository.get_profile.return_value = self._hour
        freq = update_service.update_and_return_hour_freq_for_user(self._event_log)
        self.assertIsInstance(freq, float)

    def test_update_server_new_user(self):
        update_service._profile_repository.get_profile.return_value = None
        freq = update_service.update_and_return_server_freq_for_user(self._event_log)
        self.assertIsInstance(freq, float)

    def test_update_server_old_user(self):
        update_service._profile_repository.get_profile.return_value = self._server
        freq = update_service.update_and_return_server_freq_for_user(self._event_log)
        self.assertIsInstance(freq, float)

    def test_update_ip_addr_new_user(self):
        update_service._profile_repository.get_profile.return_value = None
        freq = update_service.update_and_return_ip_freq_for_user(self._event_log)
        self.assertIsInstance(freq, float)

    def test_update_ip_addr_old_user(self):
        update_service._profile_repository.get_profile.return_value = self._ip_addr
        freq = update_service.update_and_return_ip_freq_for_user(self._event_log)
        self.assertIsInstance(freq, float)

    def test_fetch_user_no_existing(self):
        update_service._user_repository.get_by_username.return_value = None
        user = update_service.fetch_user(self._event_log)
        self.assertIsInstance(user, User)

    def test_fetch_user_existing(self):
        update_service._user_repository.get_by_username.return_value = self._user
        user = update_service.fetch_user(self._event_log)
        self.assertIsInstance(user, User)

def main():
    unittest.main()

if __name__ == "__main__":
    main()
