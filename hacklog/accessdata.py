"""Data access layer for hacklog entity persistence (DAO compatibility wrappers)."""

from collections.abc import Callable

from entities import EventLog, Profile, ProfileType, User
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
        elif isinstance(entity, Profile):
            self._profile_repository.save_profile(entity)
        else:
            raise TypeError(f"Unsupported entity type: {type(entity).__name__}")

    def merge_entity(self, entity: object) -> None:
        if isinstance(entity, User):
            self._user_repository.merge(entity)
        elif isinstance(entity, Profile):
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


class ProfileDao:
    def __init__(self, session_factory: Callable[[], Session] | None = None) -> None:
        self._profile_repository = ProfileRepository(session_factory or SessionFactory)

    def get_profile_by_user(
        self, profile_type: ProfileType, user: str
    ) -> Profile | None:
        return self._profile_repository.get_profile(profile_type, user)


class DaysDao:
    def __init__(self, session_factory: Callable[[], Session] | None = None) -> None:
        self._profile_dao = ProfileDao(session_factory)

    def get_profile_by_user(self, user: str) -> Profile | None:
        return self._profile_dao.get_profile_by_user(ProfileType.DAYS, user)


class HoursDao:
    def __init__(self, session_factory: Callable[[], Session] | None = None) -> None:
        self._profile_dao = ProfileDao(session_factory)

    def get_profile_by_user(self, user: str) -> Profile | None:
        return self._profile_dao.get_profile_by_user(ProfileType.HOURS, user)


class IpAddressDao:
    def __init__(self, session_factory: Callable[[], Session] | None = None) -> None:
        self._profile_dao = ProfileDao(session_factory)

    def get_profile_by_user(self, user: str) -> Profile | None:
        return self._profile_dao.get_profile_by_user(ProfileType.IP_ADDRESS, user)


class ServerDao:
    def __init__(self, session_factory: Callable[[], Session] | None = None) -> None:
        self._profile_dao = ProfileDao(session_factory)

    def get_profile_by_user(self, user: str) -> Profile | None:
        return self._profile_dao.get_profile_by_user(ProfileType.SERVER, user)
