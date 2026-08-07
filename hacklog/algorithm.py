"""Scoring algorithm and alert processing for authentication events."""

import math
from datetime import date

import services
from entities import EventLog, IpAddress, Threshold, User, Weight
from logging_config import get_logger

try:
    from hacklog.config import SmtpConfig
except ImportError:
    from config import SmtpConfig

logger = get_logger("algorithm")

updateService: services.UpdateService | None = None
emailService: services.EmailService | None = None


def setServices(smtp_config: SmtpConfig | None = None) -> None:
    global updateService
    global emailService
    updateService = services.UpdateService()
    emailService = services.EmailService(smtp_config)


def testProcess() -> None:
    event_log = EventLog(date.today(), "nrhine", "127.0.0.1", True, "ae1-app80-prd")
    processEventLog(event_log)


def processEventLog(eventLog: EventLog) -> None:
    auditEventLog(eventLog)
    score = calculateNewScore(eventLog)
    user = updateService.fetchUser(eventLog)
    time_diff = eventLog.date - user.lastScareDate
    updateService.updateUserScore(user, score)
    if score > Threshold.CRITICAL:
        processAlert(user, eventLog)
    elif score > Threshold.SCARY:
        if user.scareCount >= Threshold.SCARECOUNT:
            processAlert(user, eventLog)
        user = updateService.updateUserScareCount(user)
    elif abs(time_diff.days) >= Threshold.SCAREDATEEXPIRE:
        updateService.resetUserScareCount(user)


def calculateNewScore(eventLog: EventLog) -> int:
    success_score = calculateSuccessScore(eventLog.success)
    ip_location_score = calculateIpLocationScore(eventLog.ipAddress)

    server_score = calculateServerScore(eventLog)
    ip_score = calculateIpScore(eventLog)
    day_score = calculateDaysScore(eventLog)
    hour_score = calculateHoursScore(eventLog)

    total_score = (
        success_score + ip_location_score + server_score + ip_score + day_score + hour_score
    )
    logger.debug(
        "score_calculated",
        operation="calculate_score",
        username=eventLog.username,
        source_ip=eventLog.ipAddress,
        score=total_score,
    )
    return int(total_score)


def auditEventLog(eventLog: EventLog) -> None:
    updateService.auditEventLog(eventLog)


def processAlert(user: User, eventLog: EventLog) -> None:
    logger.info(
        "alert_triggered",
        operation="process_alert",
        username=user.username,
        source_ip=eventLog.ipAddress,
        score=user.score,
        server=eventLog.server,
    )
    emailService.sendEmailAlert(user, eventLog)


def calculateHoursScore(eventLog: EventLog) -> float:
    hour_freq = updateService.updateAndReturnHourFreqForUser(eventLog)
    hour_score = calculateSubscore(hour_freq) * Weight.HOURS
    return hour_score


def calculateDaysScore(eventLog: EventLog) -> float:
    day_freq = updateService.updateAndReturnDayFreqForUser(eventLog)
    day_score = calculateSubscore(day_freq) * Weight.DAYS
    return day_score


def calculateServerScore(eventLog: EventLog) -> float:
    server_freq = updateService.updateAndReturnServerFreqForUser(eventLog)
    server_score = calculateSubscore(server_freq) * Weight.SERVER
    return server_score


def calculateIpScore(eventLog: EventLog) -> float:
    ip_freq = updateService.updateAndReturnIpFreqForUser(eventLog)
    ip_score = calculateSubscore(ip_freq) * Weight.IP
    return ip_score


def calculateSubscore(freq: float) -> float:
    subscore = math.log(freq, 2)
    subscore = subscore * -10
    if subscore > 100:
        return 100.0
    return float(subscore) / 100


def calculateSuccessScore(success: bool) -> int:
    success_score = Weight.SUCCESS
    if success:
        success_score = 0
    return int(success_score)


def calculateIpLocationScore(ipAddress: str) -> int:
    ip_score = Weight.EXT
    if IpAddress.checkIpForVpn(ipAddress):
        ip_score = Weight.VPN
    if IpAddress.checkIpForInternal(ipAddress):
        ip_score = Weight.INT
    return int(ip_score)
