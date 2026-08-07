"""Generate syslog_corpus.json by exercising parse.py on Python 2.7."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'hacklog'))
from parse import Parser
from entities import SyslogMsg

SUCCESS_TEST = (
    r'Accepted\s+publickey\s+for\s+([0-9a-zA-Z_-]+)\s+from\s+'
    r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+port\s+(\d{1,4})+\s+ssh2+\s+'
    r'DATE_TIME\s+(\d{1,4}-\d{1,2}-\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+HOST\s+([\w\+%\-& ]+)'
)
FAILURE_TEST = (
    r'pam_unix\(sshd:auth\):\s+authentication\s+failure\;\s+login=\s+uid=0\s+'
    r'euid=0\s+tty=ssh+\s+ruser=+\s+rhost=(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+'
    r'user=([0-9a-zA-Z_-]+)\s+DATE_TIME\s+(\d{1,4}-\d{1,2}-\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+'
    r'HOST\s+([\w\+%\-& ]+)'
)

WINDOWS_TEMPLATE = (
    '<14>Oct {day} {time} {host} Security-Auditing: 4624: AUDIT_SUCCESS '
    'An account was successfully logged on. Subject: Security ID: S-1-5-18 '
    'Account Name: {host}$ Account Domain: WORKGROUP Logon ID: 0x3e7 '
    'Logon Type: 2 New Logon: Security ID: S-1-5-21-1223658549-3667468651-3388596622-1001 '
    'Account Name: {user} Account Domain: {domain} Logon ID: 0x8b32b5 '
    'Network Information: Workstation Name: {host} '
    'Source Network Address: {ip} Source Port: 0 '
    'Detailed Authentication Information: Logon Process: User32'
)

messages = []


def add(case_id, category, raw, host, test_enabled, success_pattern=None,
        failure_pattern=None, force_null=False):
    parser = Parser(success_pattern, failure_pattern, test_enabled)
    msg = SyslogMsg(raw, host)
    result = parser.parseLogLine(msg)
    entry = {
        'id': case_id,
        'category': category,
        'host': host,
        'test_enabled': test_enabled,
        'raw': raw,
        'expected': None,
    }
    if force_null or result is None:
        entry['expected'] = None
    else:
        exp = {
            'username': result.username,
            'ipAddress': result.ipAddress,
            'server': result.server,
            'success': result.success,
        }
        if test_enabled:
            exp['date'] = result.date.strftime('%Y-%m-%d %H:%M:%S')
        else:
            exp['date'] = None
            entry['skip_date_assertion'] = True
        entry['expected'] = exp
    messages.append(entry)


def main():
    idx = 1
    users = [
        'kantselovich', 'nrhine', 'jsmith', 'dchiu', 'msacks', 'alee',
        'mchen', 'bwong', 'tdavis', 'kpatel', 'devops',
    ]
    ips = ['10.42.10.2', '10.42.28.46', '10.42.10.22', '192.168.1.50', '172.16.0.5']

    for i, user in enumerate(users[:11]):
        ip = ips[i % len(ips)]
        port = 2000 + i
        raw = '<14>sshd[%d]: Accepted publickey for %s from %s port %d ssh2' % (
            3000 + i, user, ip, port)
        add(idx, 'linux_ssh_success', raw, '192.168.56.1', False)
        idx += 1

    for i, user in enumerate(users[:6]):
        ip = ips[i % len(ips)]
        raw = (
            '<14>sshd[%d]: Accepted publickey for %s from %s port %d ssh2 '
            'DATE_TIME 2013-09-%02d 11:%02d:48 HOST ae1-app80-prd'
        ) % (4000 + i, user, ip, 7786 + i, 10 + i, 16 + i)
        add(idx, 'linux_ssh_success', raw, '192.168.56.1', True,
            SUCCESS_TEST, FAILURE_TEST)
        idx += 1

    for i, user in enumerate(users[:11]):
        ip = ips[(i + 2) % len(ips)]
        raw = (
            '<14>sshd[%d]: pam_unix(sshd:auth): authentication failure; '
            'login= uid=0 euid=0 tty=ssh ruser= rhost=%s user=%s'
        ) % (5000 + i, ip, user)
        add(idx, 'linux_ssh_failure', raw, '192.168.56.1', False)
        idx += 1

    for i, user in enumerate(users[:6]):
        ip = ips[(i + 1) % len(ips)]
        raw = (
            '<14>sshd[%d]: pam_unix(sshd:auth): authentication failure; '
            'login= uid=0 euid=0 tty=ssh ruser= rhost=%s user=%s '
            'DATE_TIME 2013-10-%02d 14:%02d:30 HOST db-staging-02'
        ) % (6000 + i, ip, user, 5 + i, 30 + i)
        add(idx, 'linux_ssh_failure', raw, '192.168.56.1', True,
            SUCCESS_TEST, FAILURE_TEST)
        idx += 1

    windows_cases = [
        ('developer', '127.0.0.1', '10', '14:26:09'),
        ('admin', '10.24.5.10', '15', '09:15:00'),
        ('svc_backup', '10.26.8.20', '20', '22:45:33'),
        ('jsmith', '203.0.113.50', '01', '03:00:01'),
        ('mchen', '172.16.100.1', '28', '18:30:45'),
        ('alee', '10.42.1.100', '05', '12:00:00'),
    ]
    for i, (user, ip, day, time) in enumerate(windows_cases):
        host = 'WIN-DEV-%02d' % i
        raw = WINDOWS_TEMPLATE.format(
            day=day, time=time, host=host, user=user,
            domain=host.lower(), ip=ip)
        add(idx, 'windows_security_audit', raw, '192.168.56.1', False)
        idx += 1

    malformed = [
        '',
        'short',
        '<14>sshd: garbage without proper fields',
        '<14>sshd[1]: Accepted publickey for bad-ip from not-an-ip port x ssh2',
        '<14>sshd[1]: pam_unix(sshd:auth): authentication failure incomplete',
        'Oct 10 incomplete windows line without audit markers',
        '<14>Oct 10 14:26:09 HOST Security-Auditing: 4624 missing account fields',
        '<14>sshd[1]: Accepted publickey for',
        'embedded-null \x00 bytes in syslog payload',
        '<14>sshd[1]: random noise Accepted publickey',
        '<14>sshd[1]: Accepted password for user from 1.2.3.4 port 22',
    ]
    for raw in malformed:
        add(idx, 'malformed', raw, '192.168.56.1', False)
        idx += 1

    base = '<14>sshd[9999]: Accepted publickey for biguser from 10.42.10.99 port 9999 ssh2 '
    for size in [2048, 4096, 8192, 16384, 32768]:
        raw = base + ('X' * size)
        add(idx, 'oversized', raw, '192.168.56.1', False)
        idx += 1

    injections = [
        '<14>sshd[1]: Accepted publickey for admin-inject from 10.0.0.1 port 22 ssh2',
        '<14>sshd[1]: pam_unix(sshd:auth): authentication failure; login= uid=0 euid=0 tty=ssh ruser= rhost=10.0.0.2 user=sqlinject',
        '<14>sshd[1]: Accepted publickey for subshell from 10.0.0.3 port 22 ssh2',
        '<14>Oct 10 14:26:09 HOST Security-Auditing: 4624 Account Name: adminx00 Source Network Address: 127.0.0.1 extra',
        '<14>sshd[1]: Accepted publickey for path-traversal from 10.0.0.4 port 22 ssh2',
    ]
    for raw in injections:
        add(idx, 'injection', raw, '192.168.56.1', False)
        idx += 1

    edges = [
        ('<14>sshd[1]: Accepted publickey for a from 255.255.255.255 port 65535 ssh2', False),
        ('<14>sshd[1]: Accepted publickey for user_with-dash from 0.0.0.0 port 1 ssh2', False),
        (
            '<14>sshd[1]: pam_unix(sshd:auth): authentication failure; '
            'login= uid=0 euid=0 tty=ssh ruser= rhost=255.255.255.255 user=Z',
            False,
        ),
        (
            '<14>sshd[1]: Accepted publickey for UPPER from 10.42.10.2 port 2005 ssh2 '
            'DATE_TIME 2013-01-01 00:00:00 HOST srv-01',
            True,
        ),
        (
            '<14>   sshd[1]:   Accepted   publickey   for   spaced   from   '
            '10.42.10.2   port   2005   ssh2',
            False,
        ),
    ]
    for raw, test_enabled in edges:
        if test_enabled:
            add(idx, 'edge_case', raw, '10.42.10.2', True, SUCCESS_TEST, FAILURE_TEST)
        else:
            add(idx, 'edge_case', raw, '192.168.56.1', False)
        idx += 1

    out = {
        'version': 1,
        'description': 'Syslog parser golden corpus for hacklog parse.py behavioral baseline',
        'patterns': {
            'test_enabled_success': SUCCESS_TEST,
            'test_enabled_failure': FAILURE_TEST,
        },
        'message_count': len(messages),
        'messages': messages,
    }
    out_path = os.path.join(
        os.path.dirname(__file__), '..', 'tests', 'fixtures', 'syslog_corpus.json')
    out_dir = os.path.dirname(out_path)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    with open(out_path, 'w') as handle:
        json.dump(out, handle, indent=2)
    print('Wrote %d messages to %s' % (len(messages), out_path))
    cats = {}
    for msg in messages:
        cats[msg['category']] = cats.get(msg['category'], 0) + 1
    print(json.dumps(cats, indent=2))


if __name__ == '__main__':
    main()
