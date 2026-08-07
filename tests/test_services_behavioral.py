"""Behavioral tests for UpdateService profile frequency calculations."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_HACKLOG_DIR = _TESTS_DIR.parent / "hacklog"
for _path in (_HACKLOG_DIR, _TESTS_DIR.parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from entities import Days, EventLog, Hours, IpAddress, Server, User  # noqa: E402
from services import HourRangeEnum, UpdateService  # noqa: E402


@pytest.fixture
def service_event() -> EventLog:
    return EventLog(
        datetime(2026, 3, 4, 14, 30, 0),
        "behavior-user",
        "10.42.10.5",
        True,
        "web-01",
    )


def test_update_and_return_freq_for_profile_increments_counts(
    update_service: UpdateService,
) -> None:
    profile = Days(datetime(2026, 1, 1), "freq-user", {"Mon": 1}, 1)
    freq = update_service.update_and_return_freq_for_profile(profile, "Mon")
    assert freq == pytest.approx(1.0)
    assert profile.total_count == 2


@pytest.mark.parametrize(
    ("hour", "expected_range"),
    [
        (2, "early"),
        (5, "dawn"),
        (9, "morning"),
        (13, "afternoon"),
        (18, "eve"),
        (22, "night"),
    ],
)
def test_hour_ranges_cover_all_six_buckets(
    update_service: UpdateService,
    service_event: EventLog,
    hour: int,
    expected_range: str,
) -> None:
    service_event.date = service_event.date.replace(hour=hour)
    update_service.update_and_return_hour_freq_for_user(service_event)
    saved = update_service._profile_repository.get_profile(Hours, service_event.username)
    assert saved is not None
    assert expected_range in saved.profile


def test_day_profile_tracks_weekday(
    update_service: UpdateService, service_event: EventLog
) -> None:
    update_service.update_and_return_day_freq_for_user(service_event)
    saved = update_service._profile_repository.get_profile(Days, service_event.username)
    assert saved is not None
    weekday = service_event.date.strftime("%a")
    assert saved.profile[weekday] == 1


def test_server_profile_tracks_known_server(
    update_service: UpdateService, service_event: EventLog
) -> None:
    update_service.update_and_return_server_freq_for_user(service_event)
    saved = update_service._profile_repository.get_profile(Server, service_event.username)
    assert saved is not None
    assert saved.profile[service_event.server] == 1


def test_ip_profile_tracks_known_ip(
    update_service: UpdateService, service_event: EventLog
) -> None:
    update_service.update_and_return_ip_freq_for_user(service_event)
    saved = update_service._profile_repository.get_profile(IpAddress, service_event.username)
    assert saved is not None
    assert saved.profile[service_event.ip_address] == 1


def test_fetch_user_creates_new_user(update_service: UpdateService, service_event: EventLog) -> None:
    user = update_service.fetch_user(service_event)
    assert isinstance(user, User)
    assert user.username == service_event.username


def test_update_user_scare_count_returns_user(
    update_service: UpdateService, service_event: EventLog
) -> None:
    user = update_service.fetch_user(service_event)
    updated = update_service.update_user_scare_count(user)
    assert updated is not None
    assert updated.scare_count == 1


def test_audit_event_log_persists_event(
    update_service: UpdateService,
    service_event: EventLog,
    sqlite_session_factory,
) -> None:
    from sqlalchemy import select

    from entities import EventLog as EventLogEntity

    update_service.audit_event_log(service_event)
    with sqlite_session_factory() as session:
        rows = session.execute(select(EventLogEntity)).scalars().all()
    assert len(rows) == 1


def test_hour_range_enum_covers_full_day() -> None:
    covered = set()
    for hour_range in (
        HourRangeEnum.EARLY,
        HourRangeEnum.DAWN,
        HourRangeEnum.MORNING,
        HourRangeEnum.AFTERNOON,
        HourRangeEnum.EVE,
        HourRangeEnum.NIGHT,
    ):
        covered.update(hour_range)
    assert covered == set(range(24))
