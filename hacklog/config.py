"""Centralized configuration management for hacklog."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator
from pydantic.types import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class SyslogConfig(BaseModel):
    """UDP syslog listener settings."""

    bind_address: str = Field(
        default="127.0.0.1",
        description="Network address the syslog UDP listener binds to.",
    )
    port: int = Field(
        default=10514,
        ge=1,
        le=65535,
        description="UDP port for incoming syslog messages.",
    )
    max_message_size: int = Field(
        default=2048,
        ge=512,
        le=65535,
        description="Maximum syslog datagram size accepted in bytes.",
    )
    allowed_cidrs: list[str] = Field(
        default_factory=list,
        description="CIDR blocks allowed to send syslog messages to this listener.",
    )
    rate_limit_per_source: int = Field(
        default=100,
        ge=1,
        description="Maximum syslog messages accepted per source IP per second.",
    )


class SmtpConfig(BaseSettings):
    """SMTP alert delivery settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=None,
        extra="ignore",
        populate_by_name=True,
    )

    host: str = Field(
        default="smtp.gmail.com",
        validation_alias="HACKLOG_SMTP_HOST",
        description="SMTP server hostname used for alert delivery.",
    )
    port: int = Field(
        default=587,
        validation_alias="HACKLOG_SMTP_PORT",
        ge=1,
        le=65535,
        description="SMTP server port.",
    )
    username: str = Field(
        validation_alias="HACKLOG_SMTP_USER",
        description="SMTP authentication username.",
    )
    password: SecretStr = Field(
        validation_alias="HACKLOG_SMTP_PASSWORD",
        description="SMTP authentication password (required secret).",
    )
    use_tls: bool = Field(
        default=True,
        description="Enable STARTTLS when connecting to the SMTP server.",
    )
    sender: str = Field(
        validation_alias="HACKLOG_SMTP_SENDER",
        description="From address used when sending alert emails.",
    )
    recipient: str = Field(
        validation_alias="HACKLOG_ALERT_RECIPIENT",
        description="Destination address for security alert emails.",
    )

    @field_validator("password")
    @classmethod
    def validate_password_not_empty(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("HACKLOG_SMTP_PASSWORD environment variable is required")
        return value


class ScoringConfig(BaseModel):
    """Scoring engine weights and alert thresholds."""

    hours_weight: int = Field(
        default=10,
        ge=0,
        le=100,
        description=(
            "HOURS_WEIGHT: Weight applied to time-of-day anomaly sub-score. "
            "Range: 0-100. Higher values increase sensitivity to unusual login times. Default: 10"
        ),
    )
    days_weight: int = Field(
        default=10,
        ge=0,
        le=100,
        description=(
            "DAYS_WEIGHT: Weight applied to day-of-week anomaly sub-score. "
            "Range: 0-100. Higher values increase sensitivity to unusual login days. Default: 10"
        ),
    )
    server_weight: int = Field(
        default=15,
        ge=0,
        le=100,
        description=(
            "SERVER_WEIGHT: Weight applied to server access anomaly sub-score. "
            "Range: 0-100. Higher values increase sensitivity to unusual server targets. Default: 15"
        ),
    )
    success_weight: int = Field(
        default=35,
        ge=0,
        le=100,
        description=(
            "SUCCESS_WEIGHT: Weight applied to authentication success/failure sub-score. "
            "Range: 0-100. Higher values increase sensitivity to failed login patterns. Default: 35"
        ),
    )
    vpn_weight: int = Field(
        default=0,
        ge=0,
        le=100,
        description=(
            "VPN_WEIGHT: Weight applied to VPN-related location sub-score. "
            "Range: 0-100. Higher values increase VPN anomaly contribution. Default: 0"
        ),
    )
    internal_weight: int = Field(
        default=10,
        ge=0,
        le=100,
        description=(
            "INTERNAL_WEIGHT: Weight applied to internal IP location sub-score. "
            "Range: 0-100. Higher values increase sensitivity to internal IP anomalies. Default: 10"
        ),
    )
    external_weight: int = Field(
        default=15,
        ge=0,
        le=100,
        description=(
            "EXTERNAL_WEIGHT: Weight applied to external IP location sub-score. "
            "Range: 0-100. Higher values increase sensitivity to external IP anomalies. Default: 15"
        ),
    )
    ip_weight: int = Field(
        default=15,
        ge=0,
        le=100,
        description=(
            "IP_WEIGHT: Weight applied to source IP frequency sub-score. "
            "Range: 0-100. Higher values increase sensitivity to unusual source IPs. Default: 15"
        ),
    )
    critical_threshold: int = Field(
        default=50,
        ge=0,
        le=1000,
        description=(
            "CRITICAL_THRESHOLD: Total score above which an immediate alert is sent. "
            "Range: 0-1000. Lower values trigger alerts sooner. Default: 50"
        ),
    )
    scary_threshold: int = Field(
        default=30,
        ge=0,
        le=1000,
        description=(
            "SCARY_THRESHOLD: Total score above which scare-count escalation begins. "
            "Range: 0-1000. Lower values escalate repeated anomalies sooner. Default: 30"
        ),
    )
    scare_count_limit: int = Field(
        default=2,
        ge=1,
        le=100,
        description=(
            "SCARE_COUNT_LIMIT: Number of scary events before an alert is sent. "
            "Range: 1-100. Lower values alert after fewer repeated anomalies. Default: 2"
        ),
    )
    scare_date_expire_days: int = Field(
        default=1,
        ge=0,
        le=365,
        description=(
            "SCARE_DATE_EXPIRE_DAYS: Days after which user scare count resets. "
            "Range: 0-365. Lower values reset escalation counters sooner. Default: 1"
        ),
    )


class RetentionConfig(BaseModel):
    """Data retention and automated purge settings."""

    event_retention_days: int = Field(
        default=365,
        ge=1,
        le=3650,
        description=(
            "HACKLOG_EVENT_RETENTION_DAYS: Days to retain event log records. "
            "Records older than this are physically deleted. Default: 365"
        ),
    )
    profile_inactivity_days: int = Field(
        default=180,
        ge=1,
        le=3650,
        description=(
            "HACKLOG_PROFILE_INACTIVITY_DAYS: Days of inactivity after which user "
            "profiles are purged. Default: 180"
        ),
    )
    purge_schedule_hour: int = Field(
        default=2,
        ge=0,
        le=23,
        description="UTC hour at which the daily purge job runs. Default: 2 (02:00 UTC)",
    )
    purge_batch_size: int = Field(
        default=1000,
        ge=1,
        le=100000,
        description="Number of records to delete per batch to avoid long transactions. Default: 1000",
    )


class DatabaseConfig(BaseModel):
    """Database connection settings."""

    db_url: str = Field(
        default="sqlite:///hacklog.db",
        description="SQLAlchemy database URL for persistent storage.",
    )
    pool_size: int = Field(
        default=5,
        ge=1,
        le=100,
        description="SQLAlchemy connection pool size.",
    )


class SecurityConfig(BaseModel):
    """Security boundary settings."""

    allowed_source_cidrs: list[str] = Field(
        default_factory=lambda: ["0.0.0.0/0"],
        description="CIDR blocks permitted to originate syslog traffic.",
    )


class _ScoringSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HACKLOG_SCORING_", extra="ignore")

    hours_weight: int | None = None
    days_weight: int | None = None
    server_weight: int | None = None
    success_weight: int | None = None
    vpn_weight: int | None = None
    internal_weight: int | None = None
    external_weight: int | None = None
    ip_weight: int | None = None
    critical_threshold: int | None = None
    scary_threshold: int | None = None
    scare_count_limit: int | None = None
    scare_date_expire_days: int | None = None


class _SyslogSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HACKLOG_SYSLOG_", extra="ignore")

    bind_address: str | None = None
    port: int | None = None
    max_message_size: int | None = None
    allowed_cidrs: list[str] | None = None
    rate_limit_per_source: int | None = None


class _DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HACKLOG_DATABASE_", extra="ignore")

    db_url: str | None = None
    pool_size: int | None = None


class _SecuritySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HACKLOG_SECURITY_", extra="ignore")

    allowed_source_cidrs: list[str] | None = None


class _RetentionSettings(BaseSettings):
    """Reads retention env vars using HACKLOG_ prefix."""

    model_config = SettingsConfigDict(env_prefix="HACKLOG_", extra="ignore")

    event_retention_days: int | None = None
    profile_inactivity_days: int | None = None
    purge_schedule_hour: int | None = None
    purge_batch_size: int | None = None


class ConfigManager:
    """Validated hacklog configuration assembled from YAML and environment variables."""

    def __init__(
        self,
        syslog: SyslogConfig,
        smtp: SmtpConfig,
        scoring: ScoringConfig,
        database: DatabaseConfig,
        security: SecurityConfig,
        retention: RetentionConfig | None = None,
    ) -> None:
        self.syslog = syslog
        self.smtp = smtp
        self.scoring = scoring
        self.database = database
        self.security = security
        self.retention = retention or RetentionConfig()


def _load_yaml(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(
            f"Configuration file {path} must contain a YAML mapping at the top level."
        )
    return data


def _merge_non_null(base: BaseModel, overrides: dict[str, Any]) -> BaseModel:
    merged = base.model_dump()
    for key, value in overrides.items():
        if value is not None:
            merged[key] = value
    return base.model_validate(merged)


def load_config(yaml_path: str | Path | None = None) -> ConfigManager:
    """Load and validate hacklog configuration.

    Environment variables take precedence over values from the optional YAML file.
    """
    path = Path(yaml_path) if yaml_path is not None else None
    yaml_data = _load_yaml(path)

    syslog = _merge_non_null(
        SyslogConfig(**yaml_data.get("syslog", {})),
        _SyslogSettings().model_dump(),
    )
    env_allowed_cidrs = os.environ.get("HACKLOG_ALLOWED_CIDRS", "").strip()
    if env_allowed_cidrs:
        syslog = syslog.model_copy(
            update={
                "allowed_cidrs": [
                    entry.strip()
                    for entry in env_allowed_cidrs.split(",")
                    if entry.strip()
                ]
            }
        )
    scoring = _merge_non_null(
        ScoringConfig(**yaml_data.get("scoring", {})),
        _ScoringSettings().model_dump(),
    )
    database = _merge_non_null(
        DatabaseConfig(**yaml_data.get("database", {})),
        _DatabaseSettings().model_dump(),
    )
    security = _merge_non_null(
        SecurityConfig(**yaml_data.get("security", {})),
        _SecuritySettings().model_dump(),
    )
    smtp_yaml = yaml_data.get("smtp", {})
    smtp = SmtpConfig(**smtp_yaml)

    retention = _merge_non_null(
        RetentionConfig(**yaml_data.get("retention", {})),
        _RetentionSettings().model_dump(),
    )

    return ConfigManager(
        syslog=syslog,
        smtp=smtp,
        scoring=scoring,
        database=database,
        security=security,
        retention=retention,
    )


REQUIRED_SMTP_PASSWORD_MESSAGE = (
    "HACKLOG_SMTP_PASSWORD environment variable is required"
)


def _validation_error_is_missing_smtp_password(exc: ValidationError) -> bool:
    for error in exc.errors():
        location = error.get("loc", ())
        if location and location[-1] in ("password", "HACKLOG_SMTP_PASSWORD"):
            return True
        message = str(error.get("msg", ""))
        if "HACKLOG_SMTP_PASSWORD" in message:
            return True
        if error.get("type") == "missing" and any(
            part in ("password", "HACKLOG_SMTP_PASSWORD") for part in location
        ):
            return True
    return False


def load_config_or_exit(yaml_path: str | Path | None = None) -> ConfigManager:
    """Load configuration and exit with an actionable message when SMTP secrets are missing."""
    try:
        return load_config(yaml_path)
    except ValidationError as exc:
        if _validation_error_is_missing_smtp_password(exc):
            raise SystemExit(REQUIRED_SMTP_PASSWORD_MESSAGE) from exc
        raise
