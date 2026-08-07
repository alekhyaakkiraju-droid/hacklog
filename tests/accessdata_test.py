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
from entities import Days, Hours, IpAddress, Servers, User, create_db_engine, create_tables
from session import Session

genericDao = GenericDao()
userDao = UserDao()
daysDao = DaysDao()
hoursDao = HoursDao()
serverDao = ServerDao()
ipAddressDao = IpAddressDao()


class AccessDataTests(unittest.TestCase):
    def setUp(self):
        self._user = User("nrhine", datetime.today(), 10)
        self.dbFile = ":memory:"
        self.engine = create_db_engine(self)
        create_tables(self.engine)
        Session.configure(bind=self.engine)

    def tearDown(self):
        if self.dbFile != ":memory:":
            os.remove(self.dbFile)

    def test_starting_out(self):
        self.assertEqual(1, 1)

    def test_save_and_get_user(self):
        username = self._user.username
        genericDao.saveEntity(self._user)
        user_test = userDao.getUserByName(username)
        self.assertIsInstance(user_test, User)

    def test_save_and_get_day(self):
        day = Days(datetime.today(), "nrhine", {}, 0)
        genericDao.saveEntity(day)
        day_test = daysDao.getProfileByUser(self._user.username)
        self.assertIsInstance(day_test, Days)

    def test_save_and_get_hour(self):
        hours = Hours(datetime.today(), "nrhine", {}, 0)
        genericDao.saveEntity(hours)
        hours_test = hoursDao.getProfileByUser(self._user.username)
        self.assertIsInstance(hours_test, Hours)

    def test_save_and_get_server(self):
        server = Servers(datetime.today(), "nrhine", {}, 0)
        genericDao.saveEntity(server)
        server_test = serverDao.getProfileByUser(self._user.username)
        self.assertIsInstance(server_test, Servers)

    def test_save_and_get_ipAddress(self):
        ip_addr = IpAddress(datetime.today(), "nrhine", {}, 0)
        genericDao.saveEntity(ip_addr)
        ip_addr_test = ipAddressDao.getProfileByUser(self._user.username)
        self.assertIsInstance(ip_addr_test, IpAddress)

    def test_merge_user_updates_score(self):
        genericDao.saveEntity(self._user)
        self._user.score = 99
        genericDao.mergeEntity(self._user)
        merged = userDao.getUserByName(self._user.username)
        self.assertIsInstance(merged, User)
        self.assertEqual(merged.score, 99)


def main():
    unittest.main()


if __name__ == "__main__":
    main()
