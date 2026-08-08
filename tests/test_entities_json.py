"""Unit tests for JSON profile columns on the unified Profile entity."""

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select

_TESTS_DIR = Path(__file__).resolve().parent
_HACKLOG_DIR = _TESTS_DIR.parent / "hacklog"
for _path in (_HACKLOG_DIR, _TESTS_DIR.parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from entities import Profile, ProfileType, create_tables  # noqa: E402
from session import Session  # noqa: E402

@pytest.fixture
def json_db_engine(tmp_path: Path):
    db_file = tmp_path / "profiles.db"
    engine = create_engine(f"sqlite:///{db_file}")
    create_tables(engine)
    Session.configure(bind=engine)
    yield engine
    engine.dispose()

PROFILE_FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "profile_fixtures.json").read_text(
        encoding="utf-8"
    )
)

PROFILE_CASES = [
    (ProfileType.DAYS, "days"),
    (ProfileType.HOURS, "hours"),
    (ProfileType.SERVER, "servers"),
    (ProfileType.IP_ADDRESS, "ipAddress"),
]

@pytest.mark.parametrize(("profile_type", "fixture_key"), PROFILE_CASES)
def test_profile_round_trips_through_json(
    json_db_engine,
    profile_type: ProfileType,
    fixture_key: str,
) -> None:
    profile_data = PROFILE_FIXTURES[fixture_key]
    entity = Profile(
        datetime(2026, 1, 15, 12, 0, 0), "nrhine", profile_type, profile_data, 0
    )

    with Session() as session:
        session.add(entity)
        session.commit()
        loaded = session.execute(
            select(Profile).where(
                Profile.username == "nrhine",
                Profile.profile_type == profile_type.value,
            )
        ).scalar_one()
        assert loaded.profile == profile_data

@pytest.mark.parametrize(("profile_type", "fixture_key"), PROFILE_CASES)
def test_empty_profile_dict_round_trips(
    json_db_engine,
    profile_type: ProfileType,
    fixture_key: str,
) -> None:
    del fixture_key
    entity = Profile(
        datetime(2026, 2, 1, 8, 0, 0), "empty-user", profile_type, {}, 0
    )

    with Session() as session:
        session.add(entity)
        session.commit()
        loaded = session.execute(
            select(Profile).where(
                Profile.username == "empty-user",
                Profile.profile_type == profile_type.value,
            )
        ).scalar_one()
        assert loaded.profile == {}

def test_days_profile_mon_tue_example(json_db_engine) -> None:
    profile = {"Mon": 5, "Tue": 3}
    entity = Profile(
        datetime(2026, 3, 1, 0, 0, 0), "weekday-user", ProfileType.DAYS, profile, 8
    )

    with Session() as session:
        session.add(entity)
        session.commit()
        loaded = session.execute(
            select(Profile).where(
                Profile.username == "weekday-user",
                Profile.profile_type == ProfileType.DAYS.value,
            )
        ).scalar_one()
        assert loaded.profile == {"Mon": 5, "Tue": 3}
