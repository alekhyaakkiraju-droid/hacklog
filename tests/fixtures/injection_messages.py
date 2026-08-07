"""Injection payloads and valid syslog fixtures for field validation tests."""

VALID_SYSLOG_FIXTURES = {
    "success_ssh": (
        "<14>sshd[3070]: Accepted publickey for alice from 10.42.10.2 port 2005 ssh2"
    ),
    "failure_ssh": (
        "<14>sshd[3070]: pam_unix(sshd:auth): authentication failure; login= "
        "uid=0 euid=0 tty=ssh ruser= rhost=10.42.10.22 user=bob"
    ),
}

INJECTION_SYSLOG_FIXTURES = {
    "sql_username": (
        "<14>sshd[3070]: Accepted publickey for admin'; DROP TABLE users;-- from "
        "10.42.10.2 port 2005 ssh2"
    ),
    "shell_username": (
        "<14>sshd[3070]: Accepted publickey for $(whoami) from 10.42.10.2 port 2005 ssh2"
    ),
    "ldap_username": (
        "<14>sshd[3070]: Accepted publickey for admin)(|(password=*)) from "
        "10.42.10.2 port 2005 ssh2"
    ),
    "null_byte_username": (
        "<14>sshd[3070]: Accepted publickey for admin\x00evil from 10.42.10.2 port 2005 ssh2"
    ),
    "invalid_ip": (
        "<14>sshd[3070]: Accepted publickey for alice from 999.999.999.999 port 2005 ssh2"
    ),
    "invalid_hostname_test_mode": (
        "<14>sshd[4105]: Accepted publickey for alice from 10.42.10.2 port 7786 ssh2 "
        "DATE_TIME 2013-09-23 11:16:48 HOST bad host name"
    ),
}
