"""Data access layer for hacklog entity persistence."""

from sqlalchemy import select

from entities import Days, Hours, IpAddress, Servers, User
from logging_config import get_logger
from session import Session

logger = get_logger("accessdata")


class GenericDao:
    def saveEntity(self, entity: object) -> None:
        with Session() as session:
            session.add(entity)
            session.commit()
            logger.debug(
                "entity_saved",
                operation="save_entity",
                entity_type=type(entity).__name__,
            )

    def mergeEntity(self, entity: object) -> None:
        with Session() as session:
            session.merge(entity)
            session.commit()
            logger.debug(
                "entity_merged",
                operation="merge_entity",
                entity_type=type(entity).__name__,
            )


class UserDao:
    def getUserByName(self, user: str) -> User | None:
        with Session() as session:
            return session.execute(
                select(User).where(User.username == user)
            ).scalar_one_or_none()


class DaysDao:
    def getProfileByUser(self, user: str) -> Days | None:
        with Session() as session:
            return session.execute(
                select(Days).where(Days.username == user)
            ).scalar_one_or_none()


class HoursDao:
    def getProfileByUser(self, user: str) -> Hours | None:
        with Session() as session:
            return session.execute(
                select(Hours).where(Hours.username == user)
            ).scalar_one_or_none()


class IpAddressDao:
    def getProfileByUser(self, user: str) -> IpAddress | None:
        with Session() as session:
            return session.execute(
                select(IpAddress).where(IpAddress.username == user)
            ).scalar_one_or_none()


class ServerDao:
    def getProfileByUser(self, user: str) -> Servers | None:
        with Session() as session:
            return session.execute(
                select(Servers).where(Servers.username == user)
            ).scalar_one_or_none()
