import os
import sys
import unittest
from datetime import datetime
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_HACKLOG_DIR = _TESTS_DIR.parent / "hacklog"
for _path in (_TESTS_DIR, _HACKLOG_DIR, _TESTS_DIR.parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from accessdata import DaysDao, GenericDao, HoursDao, IpAddressDao, ServerDao, UserDao
from entities import (
    Profile,
    ProfileType,
    User,
    create_db_engine,
    create_tables,
)
from session import Session

generic_dao = GenericDao()
user_dao = UserDao()
days_dao = DaysDao()
hours_dao = HoursDao()
server_dao = ServerDao()
ip_address_dao = IpAddressDao()

class AccessDataTests(unittest.TestCase):
    def setUp(self):
        self._user = User("nrhine", datetime.today(), 10)
        self.db_file = ":memory:"
        self.engine = create_db_engine(self)
        create_tables(self.engine)
        Session.configure(bind=self.engine)

    def tearDown(self):
        if self.db_file != ":memory:":
            os.remove(self.db_file)

    def test_starting_out(self):
        self.assertEqual(1, 1)

    def test_save_and_get_user(self):
        username = self._user.username
        generic_dao.save_entity(self._user)
        user_test = user_dao.get_user_by_name(username)
        self.assertIsInstance(user_test, User)

    def test_save_and_get_day(self):
        day = Profile(datetime.today(), "nrhine", ProfileType.DAYS, {}, 0)
        generic_dao.save_entity(day)
        day_test = days_dao.get_profile_by_user(self._user.username)
        self.assertIsInstance(day_test, Profile)
        self.assertEqual(day_test.profile_type, ProfileType.DAYS.value)

    def test_save_and_get_hour(self):
        hours = Profile(datetime.today(), "nrhine", ProfileType.HOURS, {}, 0)
        generic_dao.save_entity(hours)
        hours_test = hours_dao.get_profile_by_user(self._user.username)
        self.assertIsInstance(hours_test, Profile)
        self.assertEqual(hours_test.profile_type, ProfileType.HOURS.value)

    def test_save_and_get_server(self):
        server = Profile(datetime.today(), "nrhine", ProfileType.SERVER, {}, 0)
        generic_dao.save_entity(server)
        server_test = server_dao.get_profile_by_user(self._user.username)
        self.assertIsInstance(server_test, Profile)
        self.assertEqual(server_test.profile_type, ProfileType.SERVER.value)

    def test_save_and_get_ip_address(self):
        ip_addr = Profile(datetime.today(), "nrhine", ProfileType.IP_ADDRESS, {}, 0)
        generic_dao.save_entity(ip_addr)
        ip_addr_test = ip_address_dao.get_profile_by_user(self._user.username)
        self.assertIsInstance(ip_addr_test, Profile)
        self.assertEqual(ip_addr_test.profile_type, ProfileType.IP_ADDRESS.value)

    def test_merge_user_updates_score(self):
        generic_dao.save_entity(self._user)
        self._user.score = 99
        generic_dao.merge_entity(self._user)
        merged = user_dao.get_user_by_name(self._user.username)
        self.assertIsInstance(merged, User)
        self.assertEqual(merged.score, 99)

def main():
    unittest.main()

if __name__ == "__main__":
    main()
