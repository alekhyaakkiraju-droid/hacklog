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

from accessdata import *
from compat import _Compat
from entities import *

genericDao = GenericDao()
userDao = UserDao()
daysDao = DaysDao()
hoursDao = HoursDao()
serverDao = ServerDao()
ipAddressDao = IpAddressDao()


class AccessDataTests(unittest.TestCase, _Compat):

    def setUp(self):
        self._user = User('nrhine', datetime.today(), 10)
        self.dbFile = ':memory:'
        create_db_engine(self)
        create_tables()

    def tearDown(self):
        if self.dbFile != ':memory:':
            os.remove(self.dbFile)

    def test_starting_out(self):
        self.assertEqual(1, 1)

    def test_save_and_get_user(self):
        username = self._user.username
        genericDao.saveEntity(self._user)
        userTest = userDao.getUserByName(username)
        self.assertIsInstance(userTest, User)

    def test_save_and_get_day(self):
        day = Days(datetime.today(), 'nrhine', {}, 0)
        genericDao.saveEntity(day)
        dayTest = daysDao.getProfileByUser(self._user.username)
        self.assertIsInstance(dayTest, Days)

    def test_save_and_get_hour(self):
        hours = Hours(datetime.today(), 'nrhine', {}, 0)
        genericDao.saveEntity(hours)
        hoursTest = hoursDao.getProfileByUser(self._user.username)
        self.assertIsInstance(hoursTest, Hours)

    def test_save_and_get_server(self):
        server = Servers(datetime.today(), 'nrhine', {}, 0)
        genericDao.saveEntity(server)
        serverTest = serverDao.getProfileByUser(self._user.username)
        self.assertIsInstance(serverTest, Servers)

    def test_save_and_get_ipAddress(self):
        ipAddr = IpAddress(datetime.today(), 'nrhine', {}, 0)
        genericDao.saveEntity(ipAddr)
        ipAddrTest = ipAddressDao.getProfileByUser(self._user.username)
        self.assertIsInstance(ipAddrTest, IpAddress)


def main():
    unittest.main()


if __name__ == "__main__":
    main()
