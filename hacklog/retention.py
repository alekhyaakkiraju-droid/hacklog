"""Data retention service with configurable purge of old event logs and profiles."""

import asyncio
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, union_all
from sqlalchemy.orm import Session

try:
    from hacklog.entities import (
        AuditRecord,
        EventLog,
        Profile,
        ProfileType,
        User,
    )
    from hacklog.logging_config import get_logger
    from hacklog.repositories import AuditRepository
except ImportError:
    from entities import (  # type: ignore[no-redef]
        AuditRecord,
        EventLog,
        Profile,
        ProfileType,
        User,
    )
    from logging_config import get_logger  # type: ignore[no-redef]
    from repositories import AuditRepository  # type: ignore[no-redef]

logger = get_logger("retention")

class DataRetentionService:
    """Purge old event logs and inactive user profiles on a configurable schedule."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        audit_repository: AuditRepository | None = None,
        *,
        event_retention_days: int = 365,
        profile_inactivity_days: int = 180,
        batch_size: int = 1000,
        purge_schedule_hour: int = 2,
    ) -> None:
        self._session_factory = session_factory
        self._audit_repository = audit_repository
        self._event_retention_days = event_retention_days
        self._profile_inactivity_days = profile_inactivity_days
        self._batch_size = batch_size
        self._purge_schedule_hour = purge_schedule_hour

    # ------------------------------------------------------------------
    # Public purge methods
    # ------------------------------------------------------------------

    def purge_event_logs(self) -> int:
        """Physically delete event log records older than the retention period.

        Uses batch deletes to avoid long-running SQLite transactions.
        Returns the total number of records deleted.
        """
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(
            days=self._event_retention_days
        )
        start = time.monotonic()
        total_deleted = 0

        while True:
            with self._session_factory() as session:
                # Select a batch of old record PKs
                batch_rows = session.execute(
                    select(EventLog.date, EventLog.username)
                    .where(EventLog.date < cutoff)
                    .limit(self._batch_size)
                ).all()

                if not batch_rows:
                    break

                # Collect dates in this batch for a targeted DELETE
                batch_dates = [row.date for row in batch_rows]
                deleted = session.execute(
                    delete(EventLog).where(EventLog.date.in_(batch_dates))
                ).rowcount
                session.commit()
                total_deleted += deleted

        elapsed = time.monotonic() - start
        logger.info(
            "event_logs_purged",
            operation="purge_event_logs",
            records_deleted=total_deleted,
            retention_days=self._event_retention_days,
            cutoff=cutoff.isoformat(),
            elapsed_seconds=round(elapsed, 3),
        )
        self._emit_audit_record(
            action="event_logs_purged",
            outcome=str(total_deleted),
            details={
                "records_deleted": total_deleted,
                "retention_days": self._event_retention_days,
                "cutoff": cutoff.isoformat(),
                "elapsed_seconds": round(elapsed, 3),
            },
        )
        return total_deleted

    def purge_inactive_profiles(self) -> int:
        """Physically delete user profiles for users inactive beyond the threshold.

        Inactivity is measured as max(date) across all profile tables and EventLog.
        Returns the total number of users purged.
        """
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(
            days=self._profile_inactivity_days
        )
        start = time.monotonic()
        total_purged = 0

        while True:
            inactive_usernames = self._find_inactive_usernames(cutoff)
            if not inactive_usernames:
                break

            for username in inactive_usernames:
                self._delete_user_records(username)
                total_purged += 1

        elapsed = time.monotonic() - start
        logger.info(
            "inactive_profiles_purged",
            operation="purge_inactive_profiles",
            users_purged=total_purged,
            inactivity_days=self._profile_inactivity_days,
            cutoff=cutoff.isoformat(),
            elapsed_seconds=round(elapsed, 3),
        )
        self._emit_audit_record(
            action="inactive_profiles_purged",
            outcome=str(total_purged),
            details={
                "users_purged": total_purged,
                "inactivity_days": self._profile_inactivity_days,
                "cutoff": cutoff.isoformat(),
                "elapsed_seconds": round(elapsed, 3),
            },
        )
        return total_purged

    def run_purge(self) -> dict[str, Any]:
        """Run both event log and profile purges; return a summary dict."""
        start = time.monotonic()
        event_logs_deleted = self.purge_event_logs()
        users_purged = self.purge_inactive_profiles()
        elapsed = time.monotonic() - start
        summary = {
            "event_logs_deleted": event_logs_deleted,
            "users_purged": users_purged,
            "elapsed_seconds": round(elapsed, 3),
            "run_at": datetime.now(UTC).isoformat(),
        }
        logger.info("purge_complete", operation="run_purge", **summary)
        return summary

    # ------------------------------------------------------------------
    # Async scheduler
    # ------------------------------------------------------------------

    async def schedule_daily_purge(self) -> None:
        """Run purge daily at the configured UTC hour; runs indefinitely."""
        logger.info(
            "purge_scheduler_started",
            operation="schedule_daily_purge",
            schedule_hour_utc=self._purge_schedule_hour,
        )
        while True:
            now = datetime.now(UTC)
            next_run = now.replace(
                hour=self._purge_schedule_hour,
                minute=0,
                second=0,
                microsecond=0,
            )
            if next_run <= now:
                next_run += timedelta(days=1)
            wait_seconds = (next_run - now).total_seconds()
            logger.info(
                "purge_scheduled",
                operation="schedule_daily_purge",
                next_run_utc=next_run.isoformat(),
                wait_seconds=round(wait_seconds, 1),
            )
            await asyncio.sleep(wait_seconds)
            try:
                await asyncio.to_thread(self.run_purge)
            except Exception:
                logger.exception(
                    "purge_error",
                    operation="schedule_daily_purge",
                )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_inactive_usernames(self, cutoff: datetime) -> list[str]:
        """Return up to batch_size usernames whose last activity is before cutoff."""
        with self._session_factory() as session:
            # Union of dates across all activity sources
            all_activity = union_all(
                select(EventLog.username.label("username"), EventLog.date.label("date")),
                select(Profile.username.label("username"), Profile.date.label("date")),
            ).subquery("all_activity")

            inactive_q = (
                select(all_activity.c.username)
                .group_by(all_activity.c.username)
                .having(func.max(all_activity.c.date) < cutoff)
                .limit(self._batch_size)
            )
            return list(session.execute(inactive_q).scalars().all())

    def _delete_user_records(self, username: str) -> None:
        """Delete all records for a username across profiles, events, and users."""
        with self._session_factory() as session:
            session.execute(delete(Profile).where(Profile.username == username))
            session.execute(delete(EventLog).where(EventLog.username == username))
            session.execute(delete(User).where(User.username == username))
            session.commit()
            logger.debug(
                "user_records_deleted",
                operation="delete_user_records",
                username=username,
            )

    def _emit_audit_record(
        self,
        action: str,
        outcome: str,
        details: dict[str, Any],
    ) -> None:
        """Emit a structured log audit entry and optionally persist to DB."""
        timestamp = datetime.now(UTC)
        logger.info(
            "audit_event",
            audit=True,
            actor="system",
            action=action,
            source_ip=None,
            resource="database",
            outcome=outcome,
            details=details,
            timestamp=timestamp.isoformat(),
        )
        if self._audit_repository is not None:
            record = AuditRecord(
                timestamp=timestamp,
                actor="system",
                source_ip=None,
                resource="database",
                action=action,
                outcome=outcome,
                details=details,
            )
            self._audit_repository.save_audit_record(record)
