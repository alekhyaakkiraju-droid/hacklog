"""Golden characterization tests for hacklog data access layer (WO-003)."""
import json
import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'hacklog'))

from accessdata import (
    GenericDao,
    UserDao,
    DaysDao,
    HoursDao,
    ServerDao,
    IpAddressDao,
)
from entities import (
    create_db_engine,
    create_tables,
    User,
    Days,
    Hours,
    Servers,
    IpAddress,
    EventLog,
)
from session import Session


FIXTURES_PATH = os.path.join(os.path.dirname(__file__), 'fixtures', 'profile_data.json')
BASE_DATE = datetime(2015, 6, 15, 14, 30, 0)


def _load_fixtures():
    with open(FIXTURES_PATH, 'r') as handle:
        return json.load(handle)


def _snapshot_user(user):
    if user is None:
        return None
    return {
        'username': user.username,
        'score': user.score,
        'scareCount': user.scareCount,
        'date': user.date,
        'lastScareDate': user.lastScareDate,
    }


def _count_rows(model):
    session = Session()
    try:
        return session.query(model).count()
    finally:
        session.close()


class AccessDataGoldenTests(unittest.TestCase):
    """Verify DAO persistence behavior against golden fixture expectations."""

    @classmethod
    def setUpClass(cls):
        cls.fixtures = _load_fixtures()
        cls.generic_dao = GenericDao()
        cls.user_dao = UserDao()
        cls.days_dao = DaysDao()
        cls.hours_dao = HoursDao()
        cls.server_dao = ServerDao()
        cls.ip_dao = IpAddressDao()

    def setUp(self):
        self.db_holder = type('DbHolder', (), {'dbFile': ':memory:'})()
        create_db_engine(self.db_holder)
        create_tables()

    def _save_and_fetch_profile(self, entity_cls, dao, username, profile, total_count):
        entity = entity_cls(BASE_DATE, username, profile, total_count)
        self.generic_dao.saveEntity(entity)
        loaded = dao.getProfileByUser(username)
        self.assertIsNotNone(loaded)
        return loaded

    def test_days_profile_round_trip_from_fixtures(self):
        for i, profile in enumerate(self.fixtures['profiles']['days']):
            total = sum(profile.values()) if profile else 0
            loaded = self._save_and_fetch_profile(
                Days, self.days_dao, 'days_user_%d' % i, profile, total)
            self.assertEqual(loaded.profile, profile)
            self.assertEqual(loaded.totalCount, total)

    def test_hours_profile_round_trip_from_fixtures(self):
        for i, profile in enumerate(self.fixtures['profiles']['hours']):
            total = sum(profile.values()) if profile else 0
            loaded = self._save_and_fetch_profile(
                Hours, self.hours_dao, 'hours_user_%d' % i, profile, total)
            self.assertEqual(loaded.profile, profile)
            self.assertEqual(loaded.totalCount, total)

    def test_servers_profile_round_trip_from_fixtures(self):
        for i, profile in enumerate(self.fixtures['profiles']['servers']):
            total = sum(profile.values()) if profile else 0
            loaded = self._save_and_fetch_profile(
                Servers, self.server_dao, 'servers_user_%d' % i, profile, total)
            self.assertEqual(loaded.profile, profile)
            self.assertEqual(loaded.totalCount, total)

    def test_ip_address_profile_round_trip_from_fixtures(self):
        for i, profile in enumerate(self.fixtures['profiles']['ipAddress']):
            total = sum(profile.values()) if profile else 0
            loaded = self._save_and_fetch_profile(
                IpAddress, self.ip_dao, 'ip_user_%d' % i, profile, total)
            self.assertEqual(loaded.profile, profile)
            self.assertEqual(loaded.totalCount, total)

    def test_user_save_fetch_and_score_update(self):
        spec = self.fixtures['users'][0]
        user = User(spec['username'], BASE_DATE, spec['score'])
        self.generic_dao.saveEntity(user)

        loaded = self.user_dao.getUserByName(spec['username'])
        snap = _snapshot_user(loaded)
        self.assertEqual(snap['username'], spec['username'])
        self.assertEqual(snap['score'], spec['score'])
        self.assertEqual(snap['scareCount'], 0)

        loaded.score = 99
        self.generic_dao.mergeEntity(loaded)
        updated = self.user_dao.getUserByName(spec['username'])
        self.assertEqual(_snapshot_user(updated)['score'], 99)

    def test_user_scare_count_update_and_reset(self):
        user = User('scare_user', BASE_DATE, 5)
        self.generic_dao.saveEntity(user)

        loaded = self.user_dao.getUserByName('scare_user')
        loaded.scareCount = 2
        loaded.lastScareDate = datetime(2015, 6, 14, 10, 0, 0)
        self.generic_dao.mergeEntity(loaded)

        reloaded = self.user_dao.getUserByName('scare_user')
        snap = _snapshot_user(reloaded)
        self.assertEqual(snap['scareCount'], 2)

        reloaded.scareCount = 0
        reloaded.lastScareDate = datetime(2015, 6, 15, 10, 0, 0)
        self.generic_dao.mergeEntity(reloaded)
        reset = self.user_dao.getUserByName('scare_user')
        self.assertEqual(_snapshot_user(reset)['scareCount'], 0)

    def test_event_log_save_and_composite_primary_key_collision(self):
        event_dt = datetime(2015, 6, 15, 14, 30, 0)
        first = EventLog(event_dt, 'nrhine', '10.42.10.2', True, 'prod-a')
        second = EventLog(event_dt, 'nrhine', '10.42.10.99', False, 'prod-b')

        self.generic_dao.saveEntity(first)

        from sqlalchemy.exc import IntegrityError
        with self.assertRaises(IntegrityError):
            self.generic_dao.saveEntity(second)

        session = Session()
        try:
            rows = session.query(EventLog).filter(
                EventLog.username == 'nrhine',
                EventLog.date == event_dt,
            ).all()
        finally:
            session.close()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].server, 'prod-a')
        self.assertEqual(rows[0].ipAddress, '10.42.10.2')

    def test_event_log_distinct_composite_keys_coexist(self):
        dt1 = datetime(2015, 6, 15, 14, 30, 0)
        dt2 = datetime(2015, 6, 15, 15, 0, 0)
        self.generic_dao.saveEntity(EventLog(dt1, 'nrhine', '1.2.3.4', True, 's1'))
        self.generic_dao.saveEntity(EventLog(dt2, 'nrhine', '5.6.7.8', False, 's2'))

        session = Session()
        try:
            count = session.query(EventLog).filter(EventLog.username == 'nrhine').count()
        finally:
            session.close()
        self.assertEqual(count, 2)

    def test_generic_dao_merge_updates_existing_user_not_duplicate(self):
        user = User('merge_user', BASE_DATE, 1)
        self.generic_dao.saveEntity(user)
        self.assertEqual(_count_rows(User), 1)

        loaded = self.user_dao.getUserByName('merge_user')
        loaded.score = 50
        self.generic_dao.mergeEntity(loaded)
        self.assertEqual(_count_rows(User), 1)

        final = self.user_dao.getUserByName('merge_user')
        self.assertEqual(_snapshot_user(final)['score'], 50)

    def test_generic_dao_merge_updates_profile_entity(self):
        profile = {'Mon': 5, 'Tue': 3}
        entity = Days(BASE_DATE, 'merge_days', profile, 8)
        self.generic_dao.saveEntity(entity)

        loaded = self.days_dao.getProfileByUser('merge_days')
        loaded.profile = {'Mon': 6, 'Tue': 3, 'Wed': 1}
        loaded.totalCount = 10
        self.generic_dao.mergeEntity(loaded)

        reloaded = self.days_dao.getProfileByUser('merge_days')
        self.assertEqual(reloaded.profile, {'Mon': 6, 'Tue': 3, 'Wed': 1})
        self.assertEqual(reloaded.totalCount, 10)
        self.assertEqual(_count_rows(Days), 1)

    def test_all_daos_fetch_saved_entities(self):
        self.generic_dao.saveEntity(User('dao_user', BASE_DATE, 7))
        self.generic_dao.saveEntity(Days(BASE_DATE, 'dao_user', {'Mon': 1}, 1))
        self.generic_dao.saveEntity(Hours(BASE_DATE, 'dao_user', {'morning': 2}, 2))
        self.generic_dao.saveEntity(Servers(BASE_DATE, 'dao_user', {'srv': 3}, 3))
        self.generic_dao.saveEntity(IpAddress(BASE_DATE, 'dao_user', {'10.0.0.1': 4}, 4))

        self.assertIsNotNone(self.user_dao.getUserByName('dao_user'))
        self.assertIsNotNone(self.days_dao.getProfileByUser('dao_user'))
        self.assertIsNotNone(self.hours_dao.getProfileByUser('dao_user'))
        self.assertIsNotNone(self.server_dao.getProfileByUser('dao_user'))
        self.assertIsNotNone(self.ip_dao.getProfileByUser('dao_user'))

    def test_uses_in_memory_sqlite_only(self):
        self.assertEqual(self.db_holder.dbFile, ':memory:')


def main():
    unittest.main()


if __name__ == '__main__':
    main()
