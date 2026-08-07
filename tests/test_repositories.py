"""Tests for repository pattern data access layer."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

_TESTS_DIR = Path(__file__).resolve().parent
_HACKLOG_DIR = _TESTS_DIR.parent / "hacklog"
for _path in (_HACKLOG_DIR, _TESTS_DIR.parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from entities import Days, EventLog, Hours, IpAddress, Servers, User, create_tables  # noqa: E402
from repositories import AuditRepository, ProfileRepository, UserRepository  # noqa: E402


@pytest.fixture
def session_factory(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'repos.db'}")
    create_tables(engine)
    factory = sessionmaker(bind=engine, autoflush=True, autocommit=False, expire_on_commit=False)
    yield factory
    engine.dispose()


@pytest.fixture
def profile_repository(session_factory) -> ProfileRepository:
    return ProfileRepository(session_factory)


@pytest.fixture
def user_repository(session_factory) -> UserRepository:
    return UserRepository(session_factory)


@pytest.fixture
def audit_repository(session_factory) -> AuditRepository:
    return AuditRepository(session_factory)


@pytest.mark.parametrize(
    ("entity_cls", "username"),
    [
        (Days, "days-user"),
        (Hours, "hours-user"),
        (Servers, "servers-user"),
        (IpAddress, "ip-user"),
    ],
)
def test_profile_repository_crud(entity_cls, username, profile_repository) -> None:
    profile = entity_cls(datetime(2026, 1, 1), username, {"Mon": 1}, 1)
    profile_repository.save_profile(profile)
    loaded = profile_repository.get_profile(entity_cls, username)
    assert loaded is not None
    assert loaded.username == username
    loaded.profile = {"Mon": 2, "Tue": 1}
    loaded.totalCount = 3
    profile_repository.update_profile(loaded)
    reloaded = profile_repository.get_profile(entity_cls, username)
    assert reloaded is not None
    assert reloaded.profile["Mon"] == 2


def test_user_repository_crud(user_repository) -> None:
    user = User("repo-user", datetime(2026, 2, 1), 10)
    user_repository.save(user)
    loaded = user_repository.get_by_username("repo-user")
    assert loaded is not None
    user_repository.update_score(loaded, 42)
    user_repository.update_scare_count(loaded)
    user_repository.reset_scare_count(loaded)
    final = user_repository.get_by_username("repo-user")
    assert final is not None
    assert final.score == 42
    assert final.scareCount == 0


def test_audit_repository_append_only(audit_repository, session_factory) -> None:
    event = EventLog(datetime(2026, 3, 1), "audit-user", "10.0.0.1", True, "host")
    audit_repository.save_event(event)
    with session_factory() as session:
        count = session.execute(select(EventLog)).scalars().all()
    assert len(count) == 1


def test_transaction_rolls_back_on_failure(profile_repository, session_factory) -> None:
    profile = Days(datetime(2026, 4, 1), "rollback-user", {"Mon": 1}, 1)
    profile_repository.save_profile(profile)

    class BrokenProfileRepository(ProfileRepository):
        def save_profile(self, profile: Days | Hours | Servers | IpAddress) -> None:
            with self.transaction() as session:
                session.add(Hours(datetime(2026, 4, 1), "rollback-user", {"early": 1}, 1))
                raise RuntimeError("forced failure")

    broken = BrokenProfileRepository(session_factory)
    with pytest.raises(RuntimeError):
        broken.save_profile(Hours(datetime(2026, 4, 1), "rollback-user", {"early": 1}, 1))

    assert profile_repository.get_profile(Hours, "rollback-user") is None
    assert profile_repository.get_profile(Days, "rollback-user") is not None


def test_repositories_use_injected_session_factory(session_factory) -> None:
    repo = ProfileRepository(session_factory)
    assert repo.session_factory is session_factory
