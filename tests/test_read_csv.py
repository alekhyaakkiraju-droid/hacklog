"""Unit tests for hacklog.read_csv CSV replay utility."""

from __future__ import annotations

import csv
import io
from datetime import datetime

import pytest

from hacklog import read_csv as read_csv_module
from hacklog.read_csv import (
    CSV_DATETIME_FORMAT_ENV,
    ReadCSVFiles,
    format_syslog_datetime,
    get_csv_datetime_format,
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


def test_parse_csv_datetime_none_logs_and_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged: list[str] = []

    def capture_error(message: str) -> None:
        logged.append(message)

    monkeypatch.setattr(read_csv_module.logger, "error", capture_error)
    with pytest.raises(ValueError, match="value cannot be None"):
        parse_csv_datetime(None)
    assert any("value cannot be None" in message for message in logged)


def test_get_csv_datetime_format_reads_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(CSV_DATETIME_FORMAT_ENV, "%Y/%m/%d %H:%M:%S")
    assert get_csv_datetime_format() == "%Y/%m/%d %H:%M:%S"


def test_parse_csv_datetime_honors_env_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(CSV_DATETIME_FORMAT_ENV, "%Y/%m/%d %H:%M:%S")
    parsed = parse_csv_datetime("2013/09/23 11:16:48")
    assert parsed == datetime(2013, 9, 23, 11, 16, 48)


def test_format_syslog_datetime_matches_parser_expectation() -> None:
    event_time = datetime(2013, 9, 23, 11, 16, 48)
    assert format_syslog_datetime(event_time) == "2013-09-23 11:16:48"


def test_log_messages_success_test_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    logged: list[str] = []
    monkeypatch.setattr(
        read_csv_module.logger,
        "info",
        lambda message: logged.append(message),
    )
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

    assert len(logged) == 1
    message = logged[0]
    assert "Accepted publickey for alice" in message
    assert "DATE_TIME 2013-09-23 11:16:48 HOST ae1-app80-prd" in message


def test_log_messages_failure_test_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    logged: list[str] = []
    monkeypatch.setattr(
        read_csv_module.logger,
        "info",
        lambda message: logged.append(message),
    )
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

    assert len(logged) == 1
    message = logged[0]
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


def test_read_line_generate_logs_skips_invalid_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    info_messages: list[str] = []
    error_messages: list[str] = []

    monkeypatch.setattr(
        read_csv_module.logger,
        "info",
        lambda message: info_messages.append(message),
    )
    monkeypatch.setattr(
        read_csv_module.logger,
        "error",
        lambda message, *args: error_messages.append(
            message % args if args else message
        ),
    )
    reader = ReadCSVFiles(test_enabled=True)
    csv_buffer = io.StringIO(
        "Date Time,User,IP,Login_Status,Server_Name\n"
        "bad-date,alice,10.0.0.1,True,srv-01\n"
        "2013-09-23 11:16:48,bob,10.0.0.2,True,srv-02\n"
    )
    reader.read_line_generate_logs(csv.reader(csv_buffer))

    assert len(info_messages) == 1
    assert "Accepted publickey for bob" in info_messages[0]
    assert any("Skipping CSV row 2" in message for message in error_messages)
