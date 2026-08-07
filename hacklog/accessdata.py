"""Data access layer for hacklog entity persistence."""

from entities import Days, Hours, IpAddress, Servers, User
from logging_config import get_logger
from session import Session

logger = get_logger("accessdata")


class GenericDao:
    def saveEntity(self, entity: object) -> None:
        session = Session()
        session.add(entity)
        session.commit()
        logger.debug(
            "entity_saved",
            operation="save_entity",
            entity_type=type(entity).__name__,
        )

    def mergeEntity(self, entity: object) -> None:
        session = Session()
        session.merge(entity)
        session.commit()
        logger.debug(
            "entity_merged",
            operation="merge_entity",
            entity_type=type(entity).__name__,
        )


class UserDao:
    def getUserByName(self, user: str) -> User | None:
        session = Session()
        full_user = session.query(User).filter(User.username == user).first()
        return full_user


class DaysDao:
    def getProfileByUser(self, user: str) -> Days | None:
        session = Session()
        days = session.query(Days).filter(Days.username == user).first()
        return days


class HoursDao:
    def getProfileByUser(self, user: str) -> Hours | None:
        session = Session()
        hours = session.query(Hours).filter(Hours.username == user).first()
        return hours


class IpAddressDao:
    def getProfileByUser(self, user: str) -> IpAddress | None:
        session = Session()
        ip_addresses = session.query(IpAddress).filter(IpAddress.username == user).first()
        return ip_addresses


class ServerDao:
    def getProfileByUser(self, user: str) -> Servers | None:
        session = Session()
        servers = session.query(Servers).filter(Servers.username == user).first()
        return servers
