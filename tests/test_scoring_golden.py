"""Golden-file characterization tests for hacklog scoring algorithm (WO-001)."""
import json
import os
import sys
import unittest
from datetime import datetime, timedelta

from mockito import mock, when, verify, unstub, any as mock_any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'hacklog'))

import algorithm
from algorithm import (
    Threshold,
    Weight,
    calculateSubscore,
    calculateSuccessScore,
    calculateIpLocationScore,
    calculateNewScore,
    processEventLog,
)
from entities import EventLog, User


FIXTURES_PATH = os.path.join(os.path.dirname(__file__), 'fixtures', 'scoring_golden.json')
TOLERANCE = 1e-10

SUBSCORE_FREQUENCIES = {
    1.0: 0.0,
    0.5: 0.1,
    0.25: 0.2,
    0.1: 0.33219280948873625,
    0.01: 0.6643856189774725,
    0.001: 0.9965784284662087,
}


def _load_golden_events():
    with open(FIXTURES_PATH, 'r') as handle:
        payload = json.load(handle)
    return payload['events']


def _parse_event(raw):
    data = raw['input']
    return EventLog(
        datetime.strptime(data['date'], '%Y-%m-%dT%H:%M:%S'),
        data['username'],
        data['ipAddress'],
        data['success'],
        data['server'],
    )


def _assert_close(test_case, actual, expected, msg=None):
    test_case.assertTrue(
        abs(actual - expected) <= TOLERANCE,
        msg or 'expected %s, got %s (delta %s)' % (expected, actual, abs(actual - expected)),
    )


class ScoringGoldenTests(unittest.TestCase):
    """Verify scoring functions match committed golden-file expectations."""

    @classmethod
    def setUpClass(cls):
        cls.golden_events = _load_golden_events()
        if len(cls.golden_events) < 500:
            raise AssertionError('fixture must contain at least 500 events')

    def setUp(self):
        self.mock_update = mock()
        self.mock_email = mock()
        algorithm.updateService = self.mock_update
        algorithm.emailService = self.mock_email

    def tearDown(self):
        unstub()

    def test_fixture_file_has_minimum_event_count(self):
        self.assertGreaterEqual(len(self.golden_events), 500)

    def test_calculate_subscore_golden_frequencies(self):
        for freq, expected in SUBSCORE_FREQUENCIES.items():
            _assert_close(self, calculateSubscore(freq), expected,
                          'calculateSubscore(%s)' % freq)

    def test_calculate_subscore_caps_at_100(self):
        # Legacy behavior: values above cap return integer 100, not 1.0
        self.assertEqual(calculateSubscore(1e-30), 100)

    def test_calculate_success_score(self):
        self.assertEqual(calculateSuccessScore(True), 0)
        self.assertEqual(calculateSuccessScore(False), Weight.SUCCESS)

    def test_calculate_ip_location_score_vpn(self):
        self.assertEqual(calculateIpLocationScore('10.42.1.100'), Weight.VPN)
        self.assertEqual(calculateIpLocationScore('10.42.255.1'), Weight.VPN)

    def test_calculate_ip_location_score_internal(self):
        self.assertEqual(calculateIpLocationScore('10.24.1.1'), Weight.INT)
        self.assertEqual(calculateIpLocationScore('10.26.50.5'), Weight.INT)
        self.assertEqual(calculateIpLocationScore('172.16.0.1'), Weight.INT)

    def test_calculate_ip_location_score_external(self):
        self.assertEqual(calculateIpLocationScore('8.8.8.8'), Weight.EXT)
        self.assertEqual(calculateIpLocationScore('203.0.113.1'), Weight.EXT)

    def test_golden_file_total_scores(self):
        for entry in self.golden_events:
            event = _parse_event(entry)
            freqs = entry['frequencies']
            expected = entry['expected']

            when(self.mock_update).updateAndReturnHourFreqForUser(event).thenReturn(freqs['hour'])
            when(self.mock_update).updateAndReturnDayFreqForUser(event).thenReturn(freqs['day'])
            when(self.mock_update).updateAndReturnServerFreqForUser(event).thenReturn(freqs['server'])
            when(self.mock_update).updateAndReturnIpFreqForUser(event).thenReturn(freqs['ip'])

            actual = calculateNewScore(event)
            _assert_close(
                self,
                actual,
                expected['total'],
                'event %s total score mismatch' % entry['id'],
            )

    def test_golden_file_dimension_scores(self):
        for entry in self.golden_events:
            event = _parse_event(entry)
            freqs = entry['frequencies']
            expected = entry['expected']

            when(self.mock_update).updateAndReturnHourFreqForUser(event).thenReturn(freqs['hour'])
            when(self.mock_update).updateAndReturnDayFreqForUser(event).thenReturn(freqs['day'])
            when(self.mock_update).updateAndReturnServerFreqForUser(event).thenReturn(freqs['server'])
            when(self.mock_update).updateAndReturnIpFreqForUser(event).thenReturn(freqs['ip'])

            _assert_close(self, calculateSuccessScore(event.success), expected['success'])
            _assert_close(self, calculateIpLocationScore(event.ipAddress), expected['ip_location'])

            hour_score = algorithm.calculateHoursScore(event)
            day_score = algorithm.calculateDaysScore(event)
            server_score = algorithm.calculateServerScore(event)
            ip_score = algorithm.calculateIpScore(event)

            _assert_close(self, hour_score, expected['hours'], 'event %s hours' % entry['id'])
            _assert_close(self, day_score, expected['days'], 'event %s days' % entry['id'])
            _assert_close(self, server_score, expected['server'], 'event %s server' % entry['id'])
            _assert_close(self, ip_score, expected['ip'], 'event %s ip' % entry['id'])


class ThresholdLogicTests(unittest.TestCase):
    """Verify alert threshold and scare-counter behavior in processEventLog."""

    def setUp(self):
        self.mock_update = mock()
        self.mock_email = mock()
        algorithm.updateService = self.mock_update
        algorithm.emailService = self.mock_email
        self.event = EventLog(datetime(2015, 6, 15, 14, 30, 0), 'nrhine', '8.8.8.8', False, 'prod')

    def tearDown(self):
        unstub()

    def _stub_profile_updates(self, hour=1.0, day=1.0, server=1.0, ip=1.0):
        when(self.mock_update).auditEventLog(mock_any()).thenReturn(None)
        when(self.mock_update).updateAndReturnHourFreqForUser(mock_any()).thenReturn(hour)
        when(self.mock_update).updateAndReturnDayFreqForUser(mock_any()).thenReturn(day)
        when(self.mock_update).updateAndReturnServerFreqForUser(mock_any()).thenReturn(server)
        when(self.mock_update).updateAndReturnIpFreqForUser(mock_any()).thenReturn(ip)
        when(self.mock_update).updateUserScore(mock_any(), mock_any()).thenReturn(None)

    def test_critical_threshold_triggers_immediate_alert(self):
        user = User('nrhine', datetime(2015, 6, 15, 14, 30, 0), 0)
        user.scareCount = 0
        user.lastScareDate = datetime(2015, 6, 14, 14, 30, 0)

        self._stub_profile_updates(hour=0.001, day=0.001, server=0.001, ip=0.001)
        when(self.mock_update).fetchUser(mock_any()).thenReturn(user)
        when(self.mock_email).sendEmailAlert(mock_any(), mock_any()).thenReturn(None)

        processEventLog(self.event)

        verify(self.mock_email, times=1).sendEmailAlert(user, self.event)

    def test_scary_threshold_with_scare_count_triggers_alert(self):
        user = User('nrhine', datetime(2015, 6, 15, 14, 30, 0), 0)
        user.scareCount = Threshold.SCARECOUNT
        user.lastScareDate = datetime(2015, 6, 14, 14, 30, 0)

        # Successful VPN login with rare profile frequencies -> score in (30, 50]
        vpn_event = EventLog(
            datetime(2015, 6, 15, 14, 30, 0), 'nrhine', '10.42.1.1', True, 'prod'
        )
        self._stub_profile_updates(hour=0.001, day=0.001, server=0.001, ip=0.001)
        when(self.mock_update).fetchUser(mock_any()).thenReturn(user)
        when(self.mock_email).sendEmailAlert(mock_any(), mock_any()).thenReturn(None)

        processEventLog(vpn_event)

        score = calculateNewScore(vpn_event)
        self.assertTrue(score > Threshold.SCARY)
        self.assertTrue(score <= Threshold.CRITICAL)
        verify(self.mock_email, times=1).sendEmailAlert(user, vpn_event)

    def test_scare_counter_resets_after_one_day_clean(self):
        user = User('nrhine', datetime(2015, 6, 15, 14, 30, 0), 0)
        user.scareCount = 1
        user.lastScareDate = datetime(2015, 6, 13, 14, 30, 0)

        clean_event = EventLog(
            datetime(2015, 6, 15, 14, 30, 0), 'nrhine', '10.42.1.1', True, 'prod'
        )

        self._stub_profile_updates()
        when(self.mock_update).fetchUser(mock_any()).thenReturn(user)
        when(self.mock_update).resetUserScareCount(user).thenReturn(None)

        processEventLog(clean_event)

        score = calculateNewScore(clean_event)
        self.assertTrue(score <= Threshold.SCARY)
        verify(self.mock_update, times=1).resetUserScareCount(user)
        verify(self.mock_email, times=0).sendEmailAlert(mock_any(), mock_any())

    def test_low_score_does_not_trigger_alert(self):
        user = User('nrhine', datetime(2015, 6, 15, 14, 30, 0), 0)
        user.scareCount = 0
        user.lastScareDate = datetime(2015, 6, 15, 10, 0, 0)

        success_event = EventLog(datetime(2015, 6, 15, 14, 30, 0), 'nrhine', '10.42.1.1', True, 'prod')

        self._stub_profile_updates()
        when(self.mock_update).fetchUser(mock_any()).thenReturn(user)

        processEventLog(success_event)

        score = calculateNewScore(success_event)
        self.assertTrue(score <= Threshold.SCARY)
        verify(self.mock_email, times=0).sendEmailAlert(mock_any(), mock_any())


def main():
    unittest.main()


if __name__ == '__main__':
    main()
