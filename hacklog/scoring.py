"""Scoring engine with injected update and alert services."""

from __future__ import annotations

import math
from datetime import date

from alerting import AlertService
from entities import EventLog, IpAddress, Threshold, User, Weight
from logging_config import get_logger
from services import UpdateService

logger = get_logger("scoring")


class ScoringEngine:
    """Score authentication events and trigger alerts using injected services."""

    def __init__(
        self,
        update_service: UpdateService,
        alert_service: AlertService,
    ) -> None:
        self._update_service = update_service
        self._alert_service = alert_service

    def processEventLog(self, event_log: EventLog) -> None:
        self.auditEventLog(event_log)
        score = self.calculateNewScore(event_log)
        user = self._update_service.fetchUser(event_log)
        time_diff = event_log.date - user.lastScareDate
        self._update_service.updateUserScore(user, score)
        if score > Threshold.CRITICAL:
            self.processAlert(user, event_log)
        elif score > Threshold.SCARY:
            if user.scareCount >= Threshold.SCARECOUNT:
                self.processAlert(user, event_log)
            user = self._update_service.updateUserScareCount(user)
        elif abs(time_diff.days) >= Threshold.SCAREDATEEXPIRE:
            self._update_service.resetUserScareCount(user)

    def calculateNewScore(self, event_log: EventLog) -> int:
        success_score = self.calculateSuccessScore(event_log.success)
        ip_location_score = self.calculateIpLocationScore(event_log.ipAddress)
        server_score = self.calculateServerScore(event_log)
        ip_score = self.calculateIpScore(event_log)
        day_score = self.calculateDaysScore(event_log)
        hour_score = self.calculateHoursScore(event_log)
        total_score = (
            success_score
            + ip_location_score
            + server_score
            + ip_score
            + day_score
            + hour_score
        )
        logger.debug(
            "score_calculated",
            operation="calculate_score",
            username=event_log.username,
            source_ip=event_log.ipAddress,
            score=total_score,
        )
        return int(total_score)

    def auditEventLog(self, event_log: EventLog) -> None:
        self._update_service.auditEventLog(event_log)

    def processAlert(self, user: User, event_log: EventLog) -> None:
        logger.info(
            "alert_triggered",
            operation="process_alert",
            username=user.username,
            source_ip=event_log.ipAddress,
            score=user.score,
            server=event_log.server,
        )
        self._alert_service.sendEmailAlert(user, event_log)

    def calculateHoursScore(self, event_log: EventLog) -> float:
        hour_freq = self._update_service.updateAndReturnHourFreqForUser(event_log)
        return self.calculateSubscore(hour_freq) * Weight.HOURS

    def calculateDaysScore(self, event_log: EventLog) -> float:
        day_freq = self._update_service.updateAndReturnDayFreqForUser(event_log)
        return self.calculateSubscore(day_freq) * Weight.DAYS

    def calculateServerScore(self, event_log: EventLog) -> float:
        server_freq = self._update_service.updateAndReturnServerFreqForUser(event_log)
        return self.calculateSubscore(server_freq) * Weight.SERVER

    def calculateIpScore(self, event_log: EventLog) -> float:
        ip_freq = self._update_service.updateAndReturnIpFreqForUser(event_log)
        return self.calculateSubscore(ip_freq) * Weight.IP

    @staticmethod
    def calculateSubscore(freq: float) -> float:
        subscore = math.log(freq, 2)
        subscore = subscore * -10
        if subscore > 100:
            return 100.0
        return float(subscore) / 100

    @staticmethod
    def calculateSuccessScore(success: bool) -> int:
        success_score = Weight.SUCCESS
        if success:
            success_score = 0
        return int(success_score)

    @staticmethod
    def calculateIpLocationScore(ip_address: str) -> int:
        ip_score = Weight.EXT
        if IpAddress.checkIpForVpn(ip_address):
            ip_score = Weight.VPN
        if IpAddress.checkIpForInternal(ip_address):
            ip_score = Weight.INT
        return int(ip_score)


def smoke_test_process(update_service: UpdateService, alert_service: AlertService) -> None:
    """Exercise scoring with injected services (development helper)."""
    engine = ScoringEngine(update_service, alert_service)
    event_log = EventLog(date.today(), "nrhine", "127.0.0.1", True, "ae1-app80-prd")
    engine.processEventLog(event_log)
