"""Unit tests for JSON profile columns on entity models."""

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

from entities import Days, Hours, IpAddress, Server, create_tables  # noqa: E402
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

ENTITY_CASES = [
    (Days, "days"),
    (Hours, "hours"),
    (Server, "servers"),
    (IpAddress, "ipAddress"),
]

@pytest.mark.parametrize(("entity_cls", "fixture_key"), ENTITY_CASES)
def test_profile_round_trips_through_json(
    json_db_engine,
    entity_cls: type,
    fixture_key: str,
) -> None:
    profile = PROFILE_FIXTURES[fixture_key]
    entity = entity_cls(datetime(2026, 1, 15, 12, 0, 0), "nrhine", profile, 0)

    with Session() as session:
        session.add(entity)
        session.commit()
        loaded = session.execute(
            select(entity_cls).where(entity_cls.username == "nrhine")
        ).scalar_one()
        assert loaded.profile == profile

@pytest.mark.parametrize(("entity_cls", "fixture_key"), ENTITY_CASES)
def test_empty_profile_dict_round_trips(
    json_db_engine,
    entity_cls: type,
    fixture_key: str,
) -> None:
    del fixture_key
    entity = entity_cls(datetime(2026, 2, 1, 8, 0, 0), "empty-user", {}, 0)

    with Session() as session:
        session.add(entity)
        session.commit()
        loaded = session.execute(
            select(entity_cls).where(entity_cls.username == "empty-user")
        ).scalar_one()
        assert loaded.profile == {}

def test_days_profile_mon_tue_example(json_db_engine) -> None:
    profile = {"Mon": 5, "Tue": 3}
    entity = Days(datetime(2026, 3, 1, 0, 0, 0), "weekday-user", profile, 8)

    with Session() as session:
        session.add(entity)
        session.commit()
        loaded = session.execute(
            select(Days).where(Days.username == "weekday-user")
        ).scalar_one()
        assert loaded.profile == {"Mon": 5, "Tue": 3}
