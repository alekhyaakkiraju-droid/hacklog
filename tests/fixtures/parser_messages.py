"""Syslog message corpus for parser behavioral tests."""

from __future__ import annotations

LINUX_SSH_SUCCESS = (
    "<14>sshd[3070]: Accepted publickey for alice from 10.42.10.2 port 2005 ssh2"
)

LINUX_SSH_FAILURE = (
    "<14>sshd[3070]: pam_unix(sshd:auth): authentication failure; login= "
    "uid=0 euid=0 tty=ssh ruser= rhost=10.42.10.22 user=bob"
)

LINUX_SSH_SUCCESS_TEST_MODE = (
    "<14>sshd[4105]: Accepted publickey for kantselovich from 10.42.10.2 "
    "port 7786 ssh2 DATE_TIME 2013-09-23 11:16:48 HOST ae1-app80-prd"
)

LINUX_SSH_FAILURE_TEST_MODE = (
    "<14>sshd[4105]: pam_unix(sshd:auth): authentication failure; login= "
    "uid=0 euid=0 tty=ssh ruser= rhost=10.42.28.46 user=dchiu "
    "DATE_TIME 2013-09-23 11:52:30 HOST ae1-app80-prd"
)

WINDOWS_AUDIT_SUCCESS = (
    "<14>Oct 10 14:26:09 USERNAME-DEV-VM Security-Auditing: 4624: AUDIT_SUCCESS "
    "An account was successfully logged on. Subject: Security ID: S-1-5-18 "
    "Account Name: USERNAME-DEV-VM$ Account Domain: WORKGROUP Logon ID: 0x3e7 "
    "Logon Type: 2 New Logon: Security ID: "
    "S-1-5-21-1223658549-3667468651-3388596622-1001 Account Name: developer "
    "Account Domain: username-dev-vm Logon ID: 0x8b32b5 Logon GUID: "
    "{00000000-0000-0000-0000-000000000000} Process Information: Process ID: "
    "0x820 Process Name: C:\\Windows\\System32\\winlogon.exe Network Information: "
    "Workstation Name: USERNAME-DEV-VM Source Network Address: 127.0.0.1 "
    "Source Port: 0 Detailed Authentication Information: Logon Process: User32 "
    "Authentication Package: Negotiate Transited Services: - Package Name "
    "(NTLM only): - Key Length: 0 This event is generated when a logon session "
    "is created."
)

MALFORMED_MESSAGES = [
    "",
    "not a syslog message",
    "<14>sshd[1]: unknown event type",
    "<14>sshd[1]: Accepted publickey for",
    "<14>sshd[1]: pam_unix(sshd:auth): authentication failure;",
    "<14>short",
    "<14>sshd[1]: Accepted publickey for user from not-an-ip port abc ssh2",
    "<14>Account Name: only-windows-fields without network address",
    "<14>Source Network Address: 1.2.3.4 without account name",
    "<14>sshd[3070]: Accepted publickey for bad ip from 999.999.999.999 port 1 ssh2",
    "<14>sshd[3070]: Accepted publickey for $(whoami) from 10.0.0.1 port 1 ssh2",
    "<14>" + "x" * 3000,
]

INJECTION_MESSAGES = {
    "sql_in_username": (
        "<14>sshd[3070]: Accepted publickey for admin'; DROP TABLE users;-- from "
        "10.42.10.2 port 2005 ssh2"
    ),
    "shell_injection_rhost": (
        "<14>sshd[3070]: pam_unix(sshd:auth): authentication failure; login= "
        "uid=0 euid=0 tty=ssh ruser= rhost=10.0.0.1;$(id) user=alice"
    ),
    "invalid_ip_after_parse": (
        "<14>sshd[3070]: Accepted publickey for alice from 999.999.999.999 port 2005 ssh2"
    ),
}
