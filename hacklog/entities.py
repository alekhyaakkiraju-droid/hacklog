"""SQLAlchemy entity models and shared constants for hacklog."""

from datetime import date, datetime
from enum import IntEnum
from typing import Any

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, create_engine
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from session import Session

db = None


class Base(DeclarativeBase):
    pass
MutableProfile = MutableDict.as_mutable(JSON)


class Weight(IntEnum):
    HOURS = 10
    DAYS = 10
    SERVER = 15
    SUCCESS = 35
    VPN = 0
    INT = 10
    EXT = 15
    IP = 15


class Threshold(IntEnum):
    CRITICAL = 50
    SCARY = 30
    SCARECOUNT = 2
    SCAREDATEEXPIRE = 1


def create_db_engine(server: Any) -> None:
    global db
    db = create_engine("sqlite:///" + server.dbFile)


def create_tables() -> None:
    Base.metadata.create_all(db)
    Session.configure(bind=db)


class EventLog(Base):
    __tablename__ = "eventLog"

    date = Column("date", DateTime, primary_key=True)
    username = Column("username", String, primary_key=True)
    ipAddress = Column("ipAddress", String)
    success = Column("success", Boolean)
    server = Column("server", String)

    def __init__(
        self,
        date: datetime,
        username: str,
        ipAddress: str,
        success: bool,
        server: str,
    ) -> None:
        self.date = date
        self.username = username
        self.ipAddress = ipAddress
        self.success = success
        self.server = server


class User(Base):
    __tablename__ = "users"

    username = Column("username", String, primary_key=True)
    date = Column("date", DateTime)
    score = Column("score", Integer)
    scareCount = Column("scareCount", Integer)
    lastScareDate = Column("lastScareDate", DateTime)

    def __init__(self, username: str, date: datetime, score: int) -> None:
        self.username = username
        self.date = date
        self.score = score
        self.scareCount = 0
        self.lastScareDate = date.today()


class Days(Base):
    __tablename__ = "days"

    date = Column("date", DateTime, primary_key=True)
    username = Column("username", String, primary_key=True)
    profile = Column("profile", MutableProfile)
    totalCount = Column("totalCount", Integer)

    def __init__(
        self,
        date: datetime,
        username: str,
        profile: dict[str, int],
        totalCount: int,
    ) -> None:
        self.date = date
        self.username = username
        self.profile = profile
        self.totalCount = totalCount


class Hours(Base):
    __tablename__ = "hours"

    date = Column("date", DateTime, primary_key=True)
    username = Column("username", String, primary_key=True)
    profile = Column("profile", MutableProfile)
    totalCount = Column("totalCount", Integer)

    def __init__(
        self,
        date: datetime,
        username: str,
        profile: dict[str, int],
        totalCount: int,
    ) -> None:
        self.date = date
        self.username = username
        self.profile = profile
        self.totalCount = totalCount


class Servers(Base):
    __tablename__ = "servers"

    date = Column("date", DateTime, primary_key=True)
    username = Column("username", String, primary_key=True)
    profile = Column("profile", MutableProfile)
    totalCount = Column("totalCount", Integer)

    def __init__(
        self,
        date: datetime,
        username: str,
        profile: dict[str, int],
        totalCount: int,
    ) -> None:
        self.date = date
        self.username = username
        self.profile = profile
        self.totalCount = totalCount


class IpAddress(Base):
    __tablename__ = "ipAddress"

    date = Column("date", DateTime, primary_key=True)
    username = Column("username", String, primary_key=True)
    profile = Column("profile", MutableProfile)
    totalCount = Column("totalCount", Integer)

    def __init__(
        self,
        date: datetime,
        username: str,
        profile: dict[str, int],
        totalCount: int,
    ) -> None:
        self.date = date
        self.username = username
        self.profile = profile
        self.totalCount = totalCount

    @staticmethod
    def checkIpForVpn(ip: str) -> bool:
        quadrant_list = ip.split(".")
        return quadrant_list[0] == "10" and quadrant_list[1] == "42"

    @staticmethod
    def checkIpForInternal(ip: str) -> bool:
        quadrant_list = ip.split(".")
        if quadrant_list[0] == "10":
            if quadrant_list[1] == "24" or quadrant_list[1] == "26":
                return True
        elif quadrant_list[0] == "172" and quadrant_list[1] == "16":
            return True
        return False


class SyslogMsg:
    def __init__(self, data: str = "", host: str = "", port: int = 0) -> None:
        self.data = data
        self.host = host
        self.port = port
        self.date = datetime.now()


class MailConf:
    def __init__(self, emailTest: bool = False) -> None:
        self.emailTest = emailTest
