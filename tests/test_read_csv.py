"""Unit tests for hacklog.read_csv CSV replay utility."""

from __future__ import annotations

from datetime import datetime

import pytest

from hacklog.read_csv import (
    ReadCSVFiles,
    format_syslog_datetime,
    parse_csv_datetime,
    resolve_csv_input_path,
)


def test_parse_csv_datetime_valid() -> None:
    parsed = parse_csv_datetime("2013-09-23 11:16:48")
    assert parsed == datetime(2013, 9, 23, 11, 16, 48)


@pytest.mark.parametrize(
    "raw_value",
    [
        "",
        "   ",
        "2013/09/23 11:16:48",
        "2013-09-23T11:16:48",
        "not-a-date",
        "2013-13-45 99:99:99",
    ],
)
def test_parse_csv_datetime_invalid_raises(raw_value: str) -> None:
    with pytest.raises(ValueError, match="Invalid Date Time"):
        parse_csv_datetime(raw_value)


def test_format_syslog_datetime_matches_parser_expectation() -> None:
    event_time = datetime(2013, 9, 23, 11, 16, 48)
    assert format_syslog_datetime(event_time) == "2013-09-23 11:16:48"


def test_log_messages_success_test_enabled(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO")
    reader = ReadCSVFiles(test_enabled=True)

    reader.log_messages(
        {
            "Date Time": "2013-09-23 11:16:48",
            "User": "alice",
            "IP": "10.42.10.2",
            "Login_Status": "True",
            "Server_Name": "ae1-app80-prd",
        }
    )

    assert len(caplog.records) == 1
    message = caplog.records[0].message
    assert "Accepted publickey for alice" in message
    assert "DATE_TIME 2013-09-23 11:16:48 HOST ae1-app80-prd" in message


def test_log_messages_failure_test_enabled(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO")
    reader = ReadCSVFiles(test_enabled=True)

    reader.log_messages(
        {
            "Date Time": "2013-10-05 14:30:30",
            "User": "bob",
            "IP": "10.42.28.46",
            "Login_Status": "FALSE",
            "Server_Name": "db-staging-02",
        }
    )

    assert len(caplog.records) == 1
    message = caplog.records[0].message
    assert "authentication failure" in message
    assert "user=bob" in message
    assert "DATE_TIME 2013-10-05 14:30:30 HOST db-staging-02" in message


def test_log_messages_missing_required_field() -> None:
    reader = ReadCSVFiles(test_enabled=True)
    with pytest.raises(ValueError, match="missing required field"):
        reader.log_messages(
            {
                "Date Time": "2013-09-23 11:16:48",
                "User": "alice",
                "IP": "10.42.10.2",
                "Login_Status": "True",
            }
        )


def test_resolve_csv_input_path_rejects_traversal(tmp_path) -> None:
    safe_file = tmp_path / "sample.csv"
    safe_file.write_text("header\n", encoding="utf-8")

    resolved = resolve_csv_input_path("sample.csv", base_dir=tmp_path)
    assert resolved == safe_file.resolve()

    with pytest.raises(ValueError, match="CSV path must stay within"):
        resolve_csv_input_path("../outside.csv", base_dir=tmp_path)
