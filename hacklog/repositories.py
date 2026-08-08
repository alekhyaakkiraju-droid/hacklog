"""Repository layer for hacklog data access."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime

from entities import AuditRecord, EventLog, Profile, ProfileType, User
from logging_config import get_logger
from sqlalchemy import select
from sqlalchemy.orm import Session

logger = get_logger("repositories")

ProfileEntity = Profile
ProfileEntityType = ProfileType

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
    """CRUD for unified Profile rows keyed by profile type and username."""

    def get_profile(
        self, profile_type: ProfileType, username: str
    ) -> Profile | None:
        with self._session_scope() as session:
            return session.execute(
                select(Profile).where(
                    Profile.profile_type == profile_type.value,
                    Profile.username == username,
                )
            ).scalar_one_or_none()

    def save_profile(self, profile: Profile) -> None:
        with self._session_scope() as session:
            session.add(profile)
            session.commit()
            logger.debug(
                "profile_saved",
                operation="save_profile",
                profile_type=profile.profile_type,
                username=profile.username,
            )

    def update_profile(self, profile: Profile) -> None:
        with self._session_scope() as session:
            session.merge(profile)
            session.commit()
            logger.debug(
                "profile_updated",
                operation="update_profile",
                profile_type=profile.profile_type,
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
        user.scare_count += 1
        user.last_scare_date = datetime.today()
        with self._session_scope() as session:
            session.merge(user)
            session.commit()
        return user

    def reset_scare_count(self, user: User) -> None:
        user.scare_count = 0
        with self._session_scope() as session:
            session.merge(user)
            session.commit()

class AuditRepository(BaseRepository):
    """Append-only event log and audit record persistence."""

    def save_event(self, event_log: EventLog) -> None:
        with self._session_scope() as session:
            session.add(event_log)
            session.commit()
            logger.debug(
                "event_log_saved",
                operation="save_event",
                username=event_log.username,
                source_ip=event_log.ip_address,
            )

    def save_audit_record(self, record: AuditRecord) -> None:
        """Persist an audit record. Append-only — no update or delete operations."""
        with self._session_scope() as session:
            session.add(record)
            session.commit()
            logger.debug(
                "audit_record_saved",
                operation="save_audit_record",
                actor=record.actor,
                action=record.action,
                resource=record.resource,
            )
