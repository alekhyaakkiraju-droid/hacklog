"""Golden-file characterization tests for hacklog syslog parser (WO-002)."""
import json
import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'hacklog'))

from parse import Parser
from entities import SyslogMsg


FIXTURES_PATH = os.path.join(os.path.dirname(__file__), 'fixtures', 'syslog_corpus.json')


def _load_corpus():
    with open(FIXTURES_PATH, 'r') as handle:
        payload = json.load(handle)
    return payload['patterns'], payload['messages']


def _build_parser(entry, patterns):
    if entry['test_enabled']:
        return Parser(
            patterns['test_enabled_success'],
            patterns['test_enabled_failure'],
            True,
        )
    return Parser(testEnabled=False)


def _assert_event_fields(test_case, actual, expected, entry):
    test_case.assertIsNotNone(actual, 'expected EventLog for case %s' % entry['id'])
    test_case.assertEqual(actual.username, expected['username'])
    test_case.assertEqual(actual.ipAddress, expected['ipAddress'])
    test_case.assertEqual(actual.server, expected['server'])
    test_case.assertEqual(actual.success, expected['success'])
    if entry.get('skip_date_assertion'):
        test_case.assertIsNotNone(actual.date)
    else:
        test_case.assertEqual(
            actual.date.strftime('%Y-%m-%d %H:%M:%S'),
            expected['date'],
        )


class ParserGoldenTests(unittest.TestCase):
    """Verify Parser.parseLogLine matches committed golden expectations."""

    @classmethod
    def setUpClass(cls):
        cls.patterns, cls.messages = _load_corpus()
        if len(cls.messages) < 50:
            raise AssertionError('fixture must contain at least 50 messages')

    def test_fixture_has_minimum_message_count(self):
        self.assertGreaterEqual(len(self.messages), 50)

    def test_category_coverage(self):
        categories = {}
        for msg in self.messages:
            categories[msg['category']] = categories.get(msg['category'], 0) + 1
        self.assertGreaterEqual(categories.get('linux_ssh_success', 0), 10)
        self.assertGreaterEqual(categories.get('linux_ssh_failure', 0), 10)
        self.assertGreaterEqual(categories.get('windows_security_audit', 0), 5)
        self.assertGreaterEqual(categories.get('malformed', 0), 10)
        self.assertGreaterEqual(categories.get('oversized', 0), 5)
        self.assertGreaterEqual(categories.get('injection', 0), 5)
        self.assertGreaterEqual(categories.get('edge_case', 0), 5)

    def test_golden_corpus_field_parity(self):
        for entry in self.messages:
            parser = _build_parser(entry, self.patterns)
            raw = entry['raw']
            if raw:
                message = SyslogMsg(raw, entry['host'])
            else:
                message = SyslogMsg('', entry['host'])
            result = parser.parseLogLine(message)
            expected = entry['expected']
            if expected is None:
                self.assertIsNone(
                    result,
                    'case %s (%s) should not parse' % (entry['id'], entry['category']),
                )
            else:
                _assert_event_fields(self, result, expected, entry)

    def test_malformed_messages_return_none_without_exception(self):
        malformed = [m for m in self.messages if m['category'] == 'malformed']
        self.assertGreaterEqual(len(malformed), 10)
        parser = Parser(testEnabled=False)
        for entry in malformed:
            raw = entry['raw']
            message = SyslogMsg(raw, entry['host']) if raw else SyslogMsg('', entry['host'])
            try:
                result = parser.parseLogLine(message)
            except Exception as exc:
                self.fail('malformed case %s raised %s' % (entry['id'], exc))
            self.assertIsNone(result, 'malformed case %s should return None' % entry['id'])

    def test_windows_account_name_and_source_network_address(self):
        windows = [m for m in self.messages if m['category'] == 'windows_security_audit']
        self.assertGreaterEqual(len(windows), 5)
        for entry in windows:
            parser = Parser(testEnabled=False)
            message = SyslogMsg(entry['raw'], entry['host'])
            result = parser.parseLogLine(message)
            self.assertIsNotNone(result)
            self.assertIn('Account Name:', entry['raw'])
            self.assertIn('Source Network Address:', entry['raw'])
            self.assertEqual(result.username, entry['expected']['username'])
            self.assertEqual(result.ipAddress, entry['expected']['ipAddress'])
            self.assertTrue(result.success)

    def test_test_enabled_and_production_modes_represented(self):
        enabled = [m for m in self.messages if m['test_enabled']]
        disabled = [m for m in self.messages if not m['test_enabled']]
        self.assertGreater(len(enabled), 0)
        self.assertGreater(len(disabled), 0)
        for entry in enabled:
            self.assertIn('date', entry['expected'])
            self.assertIsNotNone(entry['expected']['date'])


def main():
    unittest.main()


if __name__ == '__main__':
    main()
