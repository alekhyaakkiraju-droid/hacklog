"""SQLAlchemy entity models and shared constants for hacklog."""

from datetime import datetime
from enum import IntEnum
from typing import Any

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import DeclarativeBase


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


def create_db_engine(server: Any) -> Engine:
    """Create and return the SQLAlchemy engine for the configured database file."""
    return create_engine("sqlite:///" + server.db_file)


def create_tables(engine: Engine) -> None:
    """Create all entity tables on the given engine."""
    Base.metadata.create_all(engine)


class EventLog(Base):
    __tablename__ = "eventLog"

    date = Column("date", DateTime, primary_key=True)
    username = Column("username", String, primary_key=True)
    ip_address = Column("ipAddress", String)
    success = Column("success", Boolean)
    server = Column("server", String)

    def __init__(
        self,
        date: datetime,
        username: str,
        ip_address: str,
        success: bool,
        server: str,
    ) -> None:
        self.date = date
        self.username = username
        self.ip_address = ip_address
        self.success = success
        self.server = server


class User(Base):
    __tablename__ = "users"

    username = Column("username", String, primary_key=True)
    date = Column("date", DateTime)
    score = Column("score", Integer)
    scare_count = Column("scareCount", Integer)
    last_scare_date = Column("lastScareDate", DateTime)

    def __init__(self, username: str, date: datetime, score: int) -> None:
        self.username = username
        self.date = date
        self.score = score
        self.scare_count = 0
        self.last_scare_date = date.today()


class Days(Base):
    __tablename__ = "days"

    date = Column("date", DateTime, primary_key=True)
    username = Column("username", String, primary_key=True)
    profile = Column("profile", MutableProfile)
    total_count = Column("totalCount", Integer)

    def __init__(
        self,
        date: datetime,
        username: str,
        profile: dict[str, int],
        total_count: int,
    ) -> None:
        self.date = date
        self.username = username
        self.profile = profile
        self.total_count = total_count


class Hours(Base):
    __tablename__ = "hours"

    date = Column("date", DateTime, primary_key=True)
    username = Column("username", String, primary_key=True)
    profile = Column("profile", MutableProfile)
    total_count = Column("totalCount", Integer)

    def __init__(
        self,
        date: datetime,
        username: str,
        profile: dict[str, int],
        total_count: int,
    ) -> None:
        self.date = date
        self.username = username
        self.profile = profile
        self.total_count = total_count


class Server(Base):
    __tablename__ = "server"

    date = Column("date", DateTime, primary_key=True)
    username = Column("username", String, primary_key=True)
    profile = Column("profile", MutableProfile)
    total_count = Column("totalCount", Integer)

    def __init__(
        self,
        date: datetime,
        username: str,
        profile: dict[str, int],
        total_count: int,
    ) -> None:
        self.date = date
        self.username = username
        self.profile = profile
        self.total_count = total_count


class IpAddress(Base):
    __tablename__ = "ipAddress"

    date = Column("date", DateTime, primary_key=True)
    username = Column("username", String, primary_key=True)
    profile = Column("profile", MutableProfile)
    total_count = Column("totalCount", Integer)

    def __init__(
        self,
        date: datetime,
        username: str,
        profile: dict[str, int],
        total_count: int,
    ) -> None:
        self.date = date
        self.username = username
        self.profile = profile
        self.total_count = total_count

    @staticmethod
    def check_ip_for_vpn(ip: str) -> bool:
        quadrant_list = ip.split(".")
        return quadrant_list[0] == "10" and quadrant_list[1] == "42"

    @staticmethod
    def check_ip_for_internal(ip: str) -> bool:
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


class AuditRecord(Base):
    """Append-only audit record for scoring and alerting events."""

    __tablename__ = "audit_records"

    id = Column("id", Integer, primary_key=True, autoincrement=True)
    timestamp = Column("timestamp", DateTime, nullable=False)
    actor = Column("actor", String, nullable=False)
    source_ip = Column("source_ip", String, nullable=True)
    resource = Column("resource", String, nullable=True)
    action = Column("action", String, nullable=False)
    outcome = Column("outcome", String, nullable=True)
    details = Column("details", JSON, nullable=True)

    def __init__(
        self,
        timestamp: datetime,
        actor: str,
        source_ip: str | None,
        resource: str | None,
        action: str,
        outcome: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.timestamp = timestamp
        self.actor = actor
        self.source_ip = source_ip
        self.resource = resource
        self.action = action
        self.outcome = outcome
        self.details = details


class MailConf:
    def __init__(self, email_test: bool = False) -> None:
        self.email_test = email_test
