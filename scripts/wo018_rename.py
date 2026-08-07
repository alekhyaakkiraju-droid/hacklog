#!/usr/bin/env python3
"""Apply WO-018 identifier renames across Python sources."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Longest-first replacements to avoid partial matches.
REPLACEMENTS = [
    ("updateAndReturnHourFreqForUser", "update_and_return_hour_freq_for_user"),
    ("updateAndReturnDayFreqForUser", "update_and_return_day_freq_for_user"),
    ("updateAndReturnServerFreqForUser", "update_and_return_server_freq_for_user"),
    ("updateAndReturnIpFreqForUser", "update_and_return_ip_freq_for_user"),
    ("updateAndReturnFreqForProfile", "update_and_return_freq_for_profile"),
    ("calculateIpLocationScore", "calculate_ip_location_score"),
    ("calculateSuccessScore", "calculate_success_score"),
    ("calculateServerScore", "calculate_server_score"),
    ("calculateHoursScore", "calculate_hours_score"),
    ("calculateDaysScore", "calculate_days_score"),
    ("calculateSubscore", "calculate_subscore"),
    ("calculateNewScore", "calculate_new_score"),
    ("calculateIpScore", "calculate_ip_score"),
    ("getProfileByUser", "get_profile_by_user"),
    ("updateUserScareCount", "update_user_scare_count"),
    ("resetUserScareCount", "reset_user_scare_count"),
    ("checkIpForInternal", "check_ip_for_internal"),
    ("processEventLog", "process_event_log"),
    ("sendEmailAlert", "send_email_alert"),
    ("getUserByName", "get_user_by_name"),
    ("updateUserScore", "update_user_score"),
    ("checkIpForVpn", "check_ip_for_vpn"),
    ("auditEventLog", "audit_event_log"),
    ("successPattern", "success_pattern"),
    ("failurePattern", "failure_pattern"),
    ("parseLogLine", "parse_log_line"),
    ("parceConfig", "parse_config"),
    ("readCmdArgs", "read_cmd_args"),
    ("setLogging", "set_logging"),
    ("saveEntity", "save_entity"),
    ("mergeEntity", "merge_entity"),
    ("processAlert", "process_alert"),
    ("fetchUser", "fetch_user"),
    ("fromAddress", "from_address"),
    ("testEnabled", "test_enabled"),
    ("_hourRanges", "_hour_ranges"),
    ("_rangeName", "_range_name"),
    ("emailTest", "email_test"),
    ("dbFile", "db_file"),
    ("eventLog", "event_log"),
    ("ipAddr", "ip_addr"),
    ("updateService", "update_service"),
    ("emailService", "email_service"),
    ("serverDao", "server_dao"),
    ("_eventLog", "_event_log"),
    ("_ipAddr", "_ip_addr"),
]

CLASS_REPLACEMENTS = [
    (r"\bServers\b", "Server"),
]


def refactor_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    for pattern, repl in CLASS_REPLACEMENTS:
        if path.name == "001_pickle_to_json.py":
            continue
        text = re.sub(pattern, repl, text)
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def main() -> None:
    changed: list[str] = []
    for path in sorted(ROOT.rglob("*.py")):
        if ".git" in path.parts or "__pycache__" in path.parts:
            continue
        if path.name == "wo018_rename.py":
            continue
        if refactor_file(path):
            changed.append(str(path.relative_to(ROOT)))
    print(f"Updated {len(changed)} files")
    for name in changed:
        print(f"  {name}")


if __name__ == "__main__":
    main()
