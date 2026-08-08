"""WO-044: Tests for consolidated Profile entity."""

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

from entities import Profile, ProfileType  # noqa: E402
from services import UpdateService  # noqa: E402

@pytest.mark.parametrize(
    "profile_type",
    [
        ProfileType.DAYS,
        ProfileType.HOURS,
        ProfileType.SERVER,
        ProfileType.IP_ADDRESS,
    ],
)
def test_profile_entity_supports_all_legacy_profile_types(
    profile_type: ProfileType,
) -> None:
    profile = Profile(datetime(2026, 1, 1), "alice", profile_type, {"k": 1}, 1)
    assert profile.profile_type == profile_type.value


def test_update_service_creates_unified_profile_rows() -> None:
    from unittest.mock import MagicMock

    profile_repository = MagicMock()
    profile_repository.get_profile.return_value = None
    service = UpdateService(profile_repository=profile_repository)

    from entities import EventLog

    event = EventLog(datetime(2026, 1, 15, 10, 0), "bob", "10.42.10.2", True, "host")
    service.update_and_return_day_freq_for_user(event)

    saved = profile_repository.save_profile.call_args[0][0]
    assert isinstance(saved, Profile)
    assert saved.profile_type == ProfileType.DAYS.value
