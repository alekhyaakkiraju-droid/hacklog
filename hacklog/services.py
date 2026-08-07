"""Profile update services."""

from collections.abc import Callable

from entities import Days, EventLog, Hours, IpAddress, Server, User
from logging_config import get_logger
from repositories import AuditRepository, ProfileRepository, UserRepository
from session import Session as SessionFactory
from sqlalchemy.orm import Session

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
        self._hour_ranges = [
            HourRangeEnum.EARLY,
            HourRangeEnum.DAWN,
            HourRangeEnum.MORNING,
            HourRangeEnum.AFTERNOON,
            HourRangeEnum.EVE,
            HourRangeEnum.NIGHT,
        ]
        self._range_name = ["early", "dawn", "morning", "afternoon", "eve", "night"]

    def update_and_return_freq_for_profile(
        self, profile: Days | Hours | Server | IpAddress, value: str
    ) -> float:
        profile_dict = profile.profile
        profile_dict[value] = profile_dict.get(value, 0) + 1
        profile.total_count += 1
        freq = float(profile_dict[value]) / profile.total_count
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

    def update_and_return_hour_freq_for_user(self, event_log: EventLog) -> float:
        hour_profile = self._profile_repository.get_profile(Hours, event_log.username)
        hour = event_log.date.hour
        range_name = self._range_name[0]
        for hour_range in self._hour_ranges:
            if hour in hour_range:
                range_name = self._range_name[self._hour_ranges.index(hour_range)]
                break
        if hour_profile is None:
            hour_profile = Hours(event_log.date, event_log.username, {}, 0)
            self._profile_repository.save_profile(hour_profile)
        hour_freq = self.update_and_return_freq_for_profile(hour_profile, range_name)
        return hour_freq

    def update_and_return_day_freq_for_user(self, event_log: EventLog) -> float:
        day_profile = self._profile_repository.get_profile(Days, event_log.username)
        day = event_log.date.strftime("%a")
        if day_profile is None:
            day_profile = Days(event_log.date, event_log.username, {}, 0)
            self._profile_repository.save_profile(day_profile)
        day_freq = self.update_and_return_freq_for_profile(day_profile, day)
        return day_freq

    def update_and_return_server_freq_for_user(self, event_log: EventLog) -> float:
        server_profile = self._profile_repository.get_profile(
            Server, event_log.username
        )
        if server_profile is None:
            server_profile = Server(event_log.date, event_log.username, {}, 0)
            self._profile_repository.save_profile(server_profile)
        server_freq = self.update_and_return_freq_for_profile(
            server_profile, event_log.server
        )
        return server_freq

    def update_and_return_ip_freq_for_user(self, event_log: EventLog) -> float:
        ip_profile = self._profile_repository.get_profile(IpAddress, event_log.username)
        if ip_profile is None:
            ip_profile = IpAddress(event_log.date, event_log.username, {}, 0)
            self._profile_repository.save_profile(ip_profile)
        ip_freq = self.update_and_return_freq_for_profile(
            ip_profile, event_log.ip_address
        )
        return ip_freq

    def audit_event_log(self, event_log: EventLog) -> None:
        self._audit_repository.save_event(event_log)
        logger.debug(
            "event_log_audited",
            operation="audit_event_log",
            username=event_log.username,
            source_ip=event_log.ip_address,
            server=event_log.server,
        )

    def fetch_user(self, event_log: EventLog) -> User:
        user = self._user_repository.get_by_username(event_log.username)
        if user is None:
            user = User(event_log.username, event_log.date, 0)
            self._user_repository.save(user)
        return user

    def update_user_scare_count(self, user: User) -> User:
        return self._user_repository.update_scare_count(user)

    def update_user_score(self, user: User, score: int) -> None:
        self._user_repository.update_score(user, score)

    def reset_user_scare_count(self, user: User) -> None:
        self._user_repository.reset_scare_count(user)
