"""Scoring engine with injected update and alert services."""

import math
from datetime import UTC, date, datetime
from typing import Any

from alerting import AlertService
from entities import AuditRecord, EventLog, IpLocation, Threshold, User, Weight
from logging_config import get_logger
from repositories import AuditRepository
from services import UpdateService

logger = get_logger("scoring")


class ScoringEngine:
    """Score authentication events and trigger alerts using injected services."""

    def __init__(
        self,
        update_service: UpdateService,
        alert_service: AlertService,
        audit_repository: AuditRepository | None = None,
    ) -> None:
        self._update_service = update_service
        self._alert_service = alert_service
        self._audit_repository = audit_repository

    def _emit_audit_record(
        self,
        actor: str,
        action: str,
        *,
        source_ip: str | None = None,
        resource: str | None = None,
        outcome: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Emit an audit event as a structured log entry and optionally persist it."""
        timestamp = datetime.now(UTC)
        logger.info(
            "audit_event",
            audit=True,
            actor=actor,
            action=action,
            source_ip=source_ip,
            resource=resource,
            outcome=outcome,
            details=details,
            timestamp=timestamp.isoformat(),
        )
        if self._audit_repository is not None:
            record = AuditRecord(
                timestamp=timestamp,
                actor=actor,
                source_ip=source_ip,
                resource=resource,
                action=action,
                outcome=outcome,
                details=details,
            )
            self._audit_repository.save_audit_record(record)

    def process_event_log(self, event_log: EventLog) -> None:
        self.audit_event_log(event_log)
        score, dimension_scores = self.calculate_new_score(event_log)
        user = self._update_service.fetch_user(event_log)
        time_diff = event_log.date - user.last_scare_date
        self._update_service.update_user_score(user, score)
        if score > Threshold.CRITICAL:
            self._emit_audit_record(
                actor=event_log.username,
                action="score_calculated",
                source_ip=event_log.ip_address,
                resource=event_log.server,
                outcome=str(score),
                details={**dimension_scores, "alert_decision": "alert_triggered"},
            )
            self.process_alert(user, event_log)
        elif score > Threshold.SCARY:
            if user.scare_count >= Threshold.SCARECOUNT:
                self._emit_audit_record(
                    actor=event_log.username,
                    action="score_calculated",
                    source_ip=event_log.ip_address,
                    resource=event_log.server,
                    outcome=str(score),
                    details={**dimension_scores, "alert_decision": "alert_triggered"},
                )
                self.process_alert(user, event_log)
            else:
                self._emit_audit_record(
                    actor=event_log.username,
                    action="score_calculated",
                    source_ip=event_log.ip_address,
                    resource=event_log.server,
                    outcome=str(score),
                    details={**dimension_scores, "alert_decision": "scare_accumulated"},
                )
            user = self._update_service.update_user_scare_count(user)
            self._emit_audit_record(
                actor=event_log.username,
                action="scare_count_updated",
                source_ip=event_log.ip_address,
                resource=event_log.server,
                outcome=str(user.scare_count),
            )
        elif abs(time_diff.days) >= Threshold.SCAREDATEEXPIRE:
            self._emit_audit_record(
                actor=event_log.username,
                action="score_calculated",
                source_ip=event_log.ip_address,
                resource=event_log.server,
                outcome=str(score),
                details={**dimension_scores, "alert_decision": "none"},
            )
            self._update_service.reset_user_scare_count(user)
            self._emit_audit_record(
                actor=event_log.username,
                action="scare_count_reset",
                source_ip=event_log.ip_address,
                resource=event_log.server,
                outcome="0",
            )
        else:
            self._emit_audit_record(
                actor=event_log.username,
                action="score_calculated",
                source_ip=event_log.ip_address,
                resource=event_log.server,
                outcome=str(score),
                details={**dimension_scores, "alert_decision": "none"},
            )

    def calculate_new_score(self, event_log: EventLog) -> tuple[int, dict[str, float]]:
        """Calculate the risk score and return (total_score, dimension_scores)."""
        success_score = self.calculate_success_score(event_log.success)
        ip_location_score = self.calculate_ip_location_score(event_log.ip_address)
        server_score = self.calculate_server_score(event_log)
        ip_score = self.calculate_ip_score(event_log)
        day_score = self.calculate_days_score(event_log)
        hour_score = self.calculate_hours_score(event_log)
        total_score = (
            success_score
            + ip_location_score
            + server_score
            + ip_score
            + day_score
            + hour_score
        )
        dimension_scores: dict[str, float] = {
            "success_score": float(success_score),
            "ip_location_score": float(ip_location_score),
            "server_score": float(server_score),
            "ip_score": float(ip_score),
            "day_score": float(day_score),
            "hour_score": float(hour_score),
            "total_score": float(total_score),
        }
        logger.debug(
            "score_calculated",
            operation="calculate_score",
            username=event_log.username,
            source_ip=event_log.ip_address,
            score=total_score,
        )
        return int(total_score), dimension_scores

    def audit_event_log(self, event_log: EventLog) -> None:
        self._update_service.audit_event_log(event_log)

    def process_alert(self, user: User, event_log: EventLog) -> None:
        logger.info(
            "alert_triggered",
            operation="process_alert",
            username=user.username,
            source_ip=event_log.ip_address,
            score=user.score,
            server=event_log.server,
        )
        self._alert_service.send_email_alert(user, event_log)

    def calculate_hours_score(self, event_log: EventLog) -> float:
        hour_freq = self._update_service.update_and_return_hour_freq_for_user(event_log)
        return self.calculate_subscore(hour_freq) * Weight.HOURS

    def calculate_days_score(self, event_log: EventLog) -> float:
        day_freq = self._update_service.update_and_return_day_freq_for_user(event_log)
        return self.calculate_subscore(day_freq) * Weight.DAYS

    def calculate_server_score(self, event_log: EventLog) -> float:
        server_freq = self._update_service.update_and_return_server_freq_for_user(
            event_log
        )
        return self.calculate_subscore(server_freq) * Weight.SERVER

    def calculate_ip_score(self, event_log: EventLog) -> float:
        ip_freq = self._update_service.update_and_return_ip_freq_for_user(event_log)
        return self.calculate_subscore(ip_freq) * Weight.IP

    @staticmethod
    def calculate_subscore(freq: float) -> float:
        subscore = math.log(freq, 2)
        subscore = subscore * -10
        if subscore > 100:
            return 1.0
        return float(subscore) / 100

    @staticmethod
    def calculate_success_score(success: bool) -> int:
        success_score = Weight.SUCCESS
        if success:
            success_score = 0
        return int(success_score)

    @staticmethod
    def calculate_ip_location_score(ip_address: str) -> int:
        ip_score = Weight.EXT
        if IpLocation.check_ip_for_vpn(ip_address):
            ip_score = Weight.VPN
        if IpLocation.check_ip_for_internal(ip_address):
            ip_score = Weight.INT
        return int(ip_score)


def smoke_test_process(
    update_service: UpdateService, alert_service: AlertService
) -> None:
    """Exercise scoring with injected services (development helper)."""
    engine = ScoringEngine(update_service, alert_service)
    event_log = EventLog(date.today(), "nrhine", "127.0.0.1", True, "ae1-app80-prd")
    engine.process_event_log(event_log)
