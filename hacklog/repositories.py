"""Repository layer for hacklog data access."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from entities import Days, EventLog, Hours, IpAddress, Servers, User
from logging_config import get_logger

logger = get_logger("repositories")

ProfileEntity = Days | Hours | Servers | IpAddress
ProfileEntityType = type[Days] | type[Hours] | type[Servers] | type[IpAddress]
T = TypeVar("T")


class BaseRepository:
    """Base repository with injected session factory and transaction helpers."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    @property
    def session_factory(self) -> Callable[[], Session]:
        return self._session_factory

    @contextmanager
    def _session_scope(self) -> Iterator[Session]:
        with self._session_factory() as session:
            yield session

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        """Run operations in a single transaction with rollback on failure."""
        with self._session_factory() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise


class ProfileRepository(BaseRepository):
    """Parameterized CRUD for Days, Hours, Servers, and IpAddress profiles."""

    def get_profile(self, entity_class: ProfileEntityType, username: str) -> ProfileEntity | None:
        with self._session_scope() as session:
            return session.execute(
                select(entity_class).where(entity_class.username == username)
            ).scalar_one_or_none()

    def save_profile(self, profile: ProfileEntity) -> None:
        with self._session_scope() as session:
            session.add(profile)
            session.commit()
            logger.debug(
                "profile_saved",
                operation="save_profile",
                profile_type=type(profile).__name__,
                username=profile.username,
            )

    def update_profile(self, profile: ProfileEntity) -> None:
        with self._session_scope() as session:
            session.merge(profile)
            session.commit()
            logger.debug(
                "profile_updated",
                operation="update_profile",
                profile_type=type(profile).__name__,
                username=profile.username,
            )


class UserRepository(BaseRepository):
    """User entity persistence."""

    def get_by_username(self, username: str) -> User | None:
        with self._session_scope() as session:
            return session.execute(
                select(User).where(User.username == username)
            ).scalar_one_or_none()

    def save(self, user: User) -> None:
        with self._session_scope() as session:
            session.add(user)
            session.commit()
            logger.debug(
                "user_saved",
                operation="save_user",
                username=user.username,
            )

    def merge(self, user: User) -> None:
        with self._session_scope() as session:
            session.merge(user)
            session.commit()

    def update_score(self, user: User, score: int) -> None:
        user.score = score
        with self._session_scope() as session:
            session.merge(user)
            session.commit()

    def update_scare_count(self, user: User) -> User:
        user.scareCount += 1
        user.lastScareDate = datetime.today()
        with self._session_scope() as session:
            session.merge(user)
            session.commit()
        return user

    def reset_scare_count(self, user: User) -> None:
        user.scareCount = 0
        with self._session_scope() as session:
            session.merge(user)
            session.commit()


class AuditRepository(BaseRepository):
    """Append-only event log persistence."""

    def save_event(self, event_log: EventLog) -> None:
        with self._session_scope() as session:
            session.add(event_log)
            session.commit()
            logger.debug(
                "event_log_saved",
                operation="save_event",
                username=event_log.username,
                source_ip=event_log.ipAddress,
            )
