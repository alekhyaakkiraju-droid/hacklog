"""Allow-list validation for parsed syslog fields."""

import ipaddress
import re
from dataclasses import dataclass

try:
    from hacklog.logging_config import get_logger
    from hacklog.metrics import messages_dropped_total
except ImportError:
    from logging_config import get_logger
    from metrics import messages_dropped_total

logger = get_logger("validators")

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
HOSTNAME_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+$")

INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "sql_injection",
        re.compile(r"(?i)(?:;\s*drop\s+table|'\s*or\s+'1'\s*=\s*'1|union\s+select)"),
    ),
    ("shell_injection", re.compile(r"\$\(|`|\|\|")),
    ("ldap_injection", re.compile(r"\*\)|\(\||\*\(\|")),
)

@dataclass(frozen=True)
class FieldValidationResult:
    """Outcome of validating a single parsed syslog field."""

    valid: bool
    field_name: str
    reason: str | None = None

def sanitize_for_log(value: str, max_length: int = 128) -> str:
    """Return a log-safe representation of a rejected field value."""
    escaped = value.encode("unicode_escape", errors="backslashreplace").decode("ascii")
    if len(escaped) > max_length:
        return f"{escaped[:max_length]}..."
    return escaped

def _has_control_characters(value: str) -> bool:
    return any(ord(character) < 32 for character in value)

def _contains_injection_pattern(value: str) -> str | None:
    for reason, pattern in INJECTION_PATTERNS:
        if pattern.search(value):
            return reason
    return None

def validate_username(value: str) -> FieldValidationResult:
    if _has_control_characters(value):
        return FieldValidationResult(False, "username", "control_characters")
    injection = _contains_injection_pattern(value)
    if injection:
        return FieldValidationResult(False, "username", injection)
    if not USERNAME_PATTERN.fullmatch(value):
        return FieldValidationResult(False, "username", "invalid_username")
    return FieldValidationResult(True, "username")

def validate_ip_address(value: str) -> FieldValidationResult:
    if _has_control_characters(value):
        return FieldValidationResult(False, "ip_address", "control_characters")
    injection = _contains_injection_pattern(value)
    if injection:
        return FieldValidationResult(False, "ip_address", injection)
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return FieldValidationResult(False, "ip_address", "invalid_ip_address")
    return FieldValidationResult(True, "ip_address")

def validate_hostname(value: str) -> FieldValidationResult:
    if _has_control_characters(value):
        return FieldValidationResult(False, "hostname", "control_characters")
    injection = _contains_injection_pattern(value)
    if injection:
        return FieldValidationResult(False, "hostname", injection)
    if not HOSTNAME_PATTERN.fullmatch(value):
        return FieldValidationResult(False, "hostname", "invalid_hostname")
    return FieldValidationResult(True, "hostname")

def validate_parsed_fields(
    username: str,
    ip_address: str,
    hostname: str,
    *,
    meter_and_log: bool = True,
) -> bool:
    """Validate extracted syslog fields before EventLog creation."""
    checks = (
        validate_username(username),
        validate_ip_address(ip_address),
        validate_hostname(hostname),
    )
    for result in checks:
        if result.valid:
            continue
        if meter_and_log:
            field_value = {
                "username": username,
                "ip_address": ip_address,
                "hostname": hostname,
            }[result.field_name]
            messages_dropped_total.labels(reason="invalid_field").inc()
            logger.warning(
                "parsed_field_rejected",
                operation="validate_parsed_fields",
                field=result.field_name,
                reason=result.reason,
                field_value=sanitize_for_log(field_value),
            )
        return False
    return True
