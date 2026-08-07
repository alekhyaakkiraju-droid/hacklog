"""Email alerts and profile update services."""

import smtplib
from datetime import datetime

from accessdata import (
    DaysDao,
    GenericDao,
    HoursDao,
    IpAddressDao,
    ServerDao,
    UserDao,
)
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from entities import Days, EventLog, Hours, IpAddress, Servers, User
from logging_config import get_logger

try:
    from hacklog.config import SmtpConfig
except ImportError:
    from config import SmtpConfig

logger = get_logger("services")


class HourRangeEnum:
    EARLY = range(4)
    DAWN = range(4, 8)
    MORNING = range(8, 12)
    AFTERNOON = range(12, 16)
    EVE = range(16, 20)
    NIGHT = range(20, 24)


class EmailService:
    def __init__(self, smtp_config: SmtpConfig | None) -> None:
        if smtp_config is None:
            raise TypeError("EmailService requires SmtpConfig from ConfigManager")
        if not isinstance(smtp_config, SmtpConfig):
            raise TypeError("EmailService requires SmtpConfig from ConfigManager")
        self._smtp_config = smtp_config
        self.fromAddress = smtp_config.sender
        self.recipient = smtp_config.recipient
        self.mailServer: smtplib.SMTP | None = None

    def _ensure_mail_server(self) -> None:
        if self.mailServer is not None:
            return
        self.mailServer = smtplib.SMTP(self._smtp_config.host, self._smtp_config.port)
        if self._smtp_config.use_tls:
            self.mailServer.ehlo()
            self.mailServer.starttls()
            self.mailServer.ehlo()
        self.mailServer.login(
            self._smtp_config.username,
            self._smtp_config.password.get_secret_value(),
        )

    def sendMail(self, toAddress: str, msg: MIMEMultipart) -> None:
        msg["From"] = self.fromAddress
        self._ensure_mail_server()
        self.mailServer.connect()
        self.mailServer.sendmail(self.fromAddress, toAddress, msg.as_string())
        logger.info(
            "email_sent",
            operation="send_mail",
            recipient=toAddress,
        )

    def sendEmailAlert(self, user: User, eventLog: EventLog) -> None:
        to_address = self.recipient

        logger.info(
            "email_alert_prepared",
            operation="send_email_alert",
            username=user.username,
            source_ip=eventLog.ipAddress,
            server=eventLog.server,
            score=user.score,
            recipient=to_address,
        )

        msg = MIMEMultipart()
        msg["Subject"] = "EMAIL ALERT - CONCERNING SSH ACTIVITY ON: " + eventLog.server
        msg["To"] = to_address

        text = (
            "Hi!\nHow are you?\nThere was some suspicious activity on the following server: "
            + eventLog.server
            + " for user: "
            + user.username
            + "\n Their current score is "
            + str(user.score)
        )

        part = MIMEText(text, "plain")
        msg.attach(part)

        self.sendMail(to_address, msg)


class UpdateService:
    def __init__(self, conf: object | None = None) -> None:
        self._hourRanges = [
            HourRangeEnum.EARLY,
            HourRangeEnum.DAWN,
            HourRangeEnum.MORNING,
            HourRangeEnum.AFTERNOON,
            HourRangeEnum.EVE,
            HourRangeEnum.NIGHT,
        ]
        self._rangeName = ["early", "dawn", "morning", "afternoon", "eve", "night"]
        self._genericDao = GenericDao()
        self._serverDao = ServerDao()
        self._hoursDao = HoursDao()
        self._daysDao = DaysDao()
        self._ipAddressDao = IpAddressDao()
        self._userDao = UserDao()

    def updateAndReturnFreqForProfile(
        self, profile: Days | Hours | Servers | IpAddress, value: str
    ) -> float:
        profile_dict = profile.profile
        profile_dict[value] = profile_dict.get(value, 0) + 1
        profile.totalCount += 1
        freq = float(profile_dict[value]) / profile.totalCount
        profile.profile = profile_dict
        self._genericDao.mergeEntity(profile)
        logger.debug(
            "profile_frequency_updated",
            operation="update_profile_frequency",
            profile_type=type(profile).__name__,
            value=value,
            frequency=freq,
        )
        return freq

    def updateAndReturnHourFreqForUser(self, eventLog: EventLog) -> float:
        hour_profile = self._hoursDao.getProfileByUser(eventLog.username)
        hour = eventLog.date.hour
        range_name = self._rangeName[0]
        for hour_range in self._hourRanges:
            if hour in hour_range:
                range_name = self._rangeName[self._hourRanges.index(hour_range)]
                break
        if hour_profile is None:
            hour_profile = Hours(eventLog.date, eventLog.username, {}, 0)
            self._genericDao.saveEntity(hour_profile)
        hour_freq = self.updateAndReturnFreqForProfile(hour_profile, range_name)
        return hour_freq

    def updateAndReturnDayFreqForUser(self, eventLog: EventLog) -> float:
        day_profile = self._daysDao.getProfileByUser(eventLog.username)
        day = eventLog.date.strftime("%a")
        if day_profile is None:
            day_profile = Days(eventLog.date, eventLog.username, {}, 0)
            self._genericDao.saveEntity(day_profile)
        day_freq = self.updateAndReturnFreqForProfile(day_profile, day)
        return day_freq

    def updateAndReturnServerFreqForUser(self, eventLog: EventLog) -> float:
        server_profile = self._serverDao.getProfileByUser(eventLog.username)
        if server_profile is None:
            server_profile = Servers(eventLog.date, eventLog.username, {}, 0)
            self._genericDao.saveEntity(server_profile)
        server_freq = self.updateAndReturnFreqForProfile(server_profile, eventLog.server)
        return server_freq

    def updateAndReturnIpFreqForUser(self, eventLog: EventLog) -> float:
        ip_profile = self._ipAddressDao.getProfileByUser(eventLog.username)
        if ip_profile is None:
            ip_profile = IpAddress(eventLog.date, eventLog.username, {}, 0)
            self._genericDao.saveEntity(ip_profile)
        ip_freq = self.updateAndReturnFreqForProfile(ip_profile, eventLog.ipAddress)
        return ip_freq

    def auditEventLog(self, eventLog: EventLog) -> None:
        self._genericDao.saveEntity(eventLog)
        logger.debug(
            "event_log_audited",
            operation="audit_event_log",
            username=eventLog.username,
            source_ip=eventLog.ipAddress,
            server=eventLog.server,
        )

    def fetchUser(self, eventLog: EventLog) -> User:
        user = self._userDao.getUserByName(eventLog.username)
        if user is None:
            user = User(eventLog.username, eventLog.date, 0)
            self._genericDao.saveEntity(user)
        return user

    def updateUserScareCount(self, user: User) -> User:
        user.scareCount += 1
        user.lastScareDate = datetime.today()
        self._genericDao.mergeEntity(user)
        return user

    def updateUserScore(self, user: User, score: int) -> None:
        user.score = score
        self._genericDao.mergeEntity(user)

    def resetUserScareCount(self, user: User) -> None:
        user.scareCount = 0
        self._genericDao.mergeEntity(user)
