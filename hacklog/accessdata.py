"""Data access layer for hacklog entity persistence (DAO compatibility wrappers)."""

from collections.abc import Callable

from entities import Days, EventLog, Hours, IpAddress, Server, User
from repositories import AuditRepository, ProfileRepository, UserRepository
from session import Session as SessionFactory
from sqlalchemy.orm import Session

class GenericDao:
    def __init__(self, session_factory: Callable[[], Session] | None = None) -> None:
        factory = session_factory or SessionFactory
        self._profile_repository = ProfileRepository(factory)
        self._user_repository = UserRepository(factory)
        self._audit_repository = AuditRepository(factory)

    def save_entity(self, entity: object) -> None:
        if isinstance(entity, EventLog):
            self._audit_repository.save_event(entity)
        elif isinstance(entity, User):
            self._user_repository.save(entity)
        elif isinstance(entity, (Days, Hours, Server, IpAddress)):
            self._profile_repository.save_profile(entity)
        else:
            raise TypeError(f"Unsupported entity type: {type(entity).__name__}")

    def merge_entity(self, entity: object) -> None:
        if isinstance(entity, User):
            self._user_repository.merge(entity)
        elif isinstance(entity, (Days, Hours, Server, IpAddress)):
            self._profile_repository.update_profile(entity)
        else:
            raise TypeError(
                f"Unsupported entity type for merge: {type(entity).__name__}"
            )

class UserDao:
    def __init__(self, session_factory: Callable[[], Session] | None = None) -> None:
        self._user_repository = UserRepository(session_factory or SessionFactory)

    def get_user_by_name(self, user: str) -> User | None:
        return self._user_repository.get_by_username(user)

class DaysDao:
    def __init__(self, session_factory: Callable[[], Session] | None = None) -> None:
        self._profile_repository = ProfileRepository(session_factory or SessionFactory)

    def get_profile_by_user(self, user: str) -> Days | None:
        profile = self._profile_repository.get_profile(Days, user)
        return profile if isinstance(profile, Days) else None

class HoursDao:
    def __init__(self, session_factory: Callable[[], Session] | None = None) -> None:
        self._profile_repository = ProfileRepository(session_factory or SessionFactory)

    def get_profile_by_user(self, user: str) -> Hours | None:
        profile = self._profile_repository.get_profile(Hours, user)
        return profile if isinstance(profile, Hours) else None

class IpAddressDao:
    def __init__(self, session_factory: Callable[[], Session] | None = None) -> None:
        self._profile_repository = ProfileRepository(session_factory or SessionFactory)

    def get_profile_by_user(self, user: str) -> IpAddress | None:
        profile = self._profile_repository.get_profile(IpAddress, user)
        return profile if isinstance(profile, IpAddress) else None

class ServerDao:
    def __init__(self, session_factory: Callable[[], Session] | None = None) -> None:
        self._profile_repository = ProfileRepository(session_factory or SessionFactory)

    def get_profile_by_user(self, user: str) -> Server | None:
        profile = self._profile_repository.get_profile(Server, user)
        return profile if isinstance(profile, Server) else None
