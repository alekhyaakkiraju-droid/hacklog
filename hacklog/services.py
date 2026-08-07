"""Profile update services."""

from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session

from entities import Days, EventLog, Hours, IpAddress, Servers, User
from logging_config import get_logger
from repositories import AuditRepository, ProfileRepository, UserRepository
from session import Session as SessionFactory

logger = get_logger("services")


class HourRangeEnum:
    EARLY = range(4)
    DAWN = range(4, 8)
    MORNING = range(8, 12)
    AFTERNOON = range(12, 16)
    EVE = range(16, 20)
    NIGHT = range(20, 24)


class UpdateService:
    def __init__(
        self,
        conf: object | None = None,
        *,
        session_factory: Callable[[], Session] | None = None,
        profile_repository: ProfileRepository | None = None,
        user_repository: UserRepository | None = None,
        audit_repository: AuditRepository | None = None,
    ) -> None:
        del conf
        factory = session_factory or SessionFactory
        self._profile_repository = profile_repository or ProfileRepository(factory)
        self._user_repository = user_repository or UserRepository(factory)
        self._audit_repository = audit_repository or AuditRepository(factory)
        self._hourRanges = [
            HourRangeEnum.EARLY,
            HourRangeEnum.DAWN,
            HourRangeEnum.MORNING,
            HourRangeEnum.AFTERNOON,
            HourRangeEnum.EVE,
            HourRangeEnum.NIGHT,
        ]
        self._rangeName = ["early", "dawn", "morning", "afternoon", "eve", "night"]

    def updateAndReturnFreqForProfile(
        self, profile: Days | Hours | Servers | IpAddress, value: str
    ) -> float:
        profile_dict = profile.profile
        profile_dict[value] = profile_dict.get(value, 0) + 1
        profile.totalCount += 1
        freq = float(profile_dict[value]) / profile.totalCount
        profile.profile = profile_dict
        self._profile_repository.update_profile(profile)
        logger.debug(
            "profile_frequency_updated",
            operation="update_profile_frequency",
            profile_type=type(profile).__name__,
            value=value,
            frequency=freq,
        )
        return freq

    def updateAndReturnHourFreqForUser(self, eventLog: EventLog) -> float:
        hour_profile = self._profile_repository.get_profile(Hours, eventLog.username)
        hour = eventLog.date.hour
        range_name = self._rangeName[0]
        for hour_range in self._hourRanges:
            if hour in hour_range:
                range_name = self._rangeName[self._hourRanges.index(hour_range)]
                break
        if hour_profile is None:
            hour_profile = Hours(eventLog.date, eventLog.username, {}, 0)
            self._profile_repository.save_profile(hour_profile)
        hour_freq = self.updateAndReturnFreqForProfile(hour_profile, range_name)
        return hour_freq

    def updateAndReturnDayFreqForUser(self, eventLog: EventLog) -> float:
        day_profile = self._profile_repository.get_profile(Days, eventLog.username)
        day = eventLog.date.strftime("%a")
        if day_profile is None:
            day_profile = Days(eventLog.date, eventLog.username, {}, 0)
            self._profile_repository.save_profile(day_profile)
        day_freq = self.updateAndReturnFreqForProfile(day_profile, day)
        return day_freq

    def updateAndReturnServerFreqForUser(self, eventLog: EventLog) -> float:
        server_profile = self._profile_repository.get_profile(Servers, eventLog.username)
        if server_profile is None:
            server_profile = Servers(eventLog.date, eventLog.username, {}, 0)
            self._profile_repository.save_profile(server_profile)
        server_freq = self.updateAndReturnFreqForProfile(server_profile, eventLog.server)
        return server_freq

    def updateAndReturnIpFreqForUser(self, eventLog: EventLog) -> float:
        ip_profile = self._profile_repository.get_profile(IpAddress, eventLog.username)
        if ip_profile is None:
            ip_profile = IpAddress(eventLog.date, eventLog.username, {}, 0)
            self._profile_repository.save_profile(ip_profile)
        ip_freq = self.updateAndReturnFreqForProfile(ip_profile, eventLog.ipAddress)
        return ip_freq

    def auditEventLog(self, eventLog: EventLog) -> None:
        self._audit_repository.save_event(eventLog)
        logger.debug(
            "event_log_audited",
            operation="audit_event_log",
            username=eventLog.username,
            source_ip=eventLog.ipAddress,
            server=eventLog.server,
        )

    def fetchUser(self, eventLog: EventLog) -> User:
        user = self._user_repository.get_by_username(eventLog.username)
        if user is None:
            user = User(eventLog.username, eventLog.date, 0)
            self._user_repository.save(user)
        return user

    def updateUserScareCount(self, user: User) -> User:
        return self._user_repository.update_scare_count(user)

    def updateUserScore(self, user: User, score: int) -> None:
        self._user_repository.update_score(user, score)

    def resetUserScareCount(self, user: User) -> None:
        self._user_repository.reset_scare_count(user)
