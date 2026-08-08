"""Structured logging configuration for hacklog using structlog."""

import json
import logging
import re
import sys
from typing import Any

import structlog
from pydantic.types import SecretStr

_SENSITIVE_KEY_PATTERN = re.compile(
    r"password|secret|token|credential|api_key",
    re.IGNORECASE,
)

_MASK_PII = False


def _mask_value(value: str) -> str:
    if len(value) <= 4:
        return "****"
    return f"{value[:2]}****{value[-2:]}"


def _redact_secrets(
    _logger: Any,
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in event_dict.items():
        if _SENSITIVE_KEY_PATTERN.search(key):
            redacted[key] = "***REDACTED***"
        elif isinstance(value, SecretStr):
            redacted[key] = "***REDACTED***"
        elif isinstance(value, dict):
            redacted[key] = {
                nested_key: (
                    "***REDACTED***"
                    if _SENSITIVE_KEY_PATTERN.search(nested_key)
                    else nested_value
                )
                for nested_key, nested_value in value.items()
            }
        else:
            redacted[key] = value
    return redacted


def _mask_pii(
    _logger: Any,
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    if not _MASK_PII:
        return event_dict

    level_name = event_dict.get("level", event_dict.get("log_level", "info"))
    if isinstance(level_name, int):
        level_name = logging.getLevelName(level_name).lower()
    elif isinstance(level_name, str):
        level_name = level_name.lower()
    else:
        level_name = "info"

    if level_name == "debug":
        for key in ("username", "source_ip", "ip_address"):
            value = event_dict.get(key)
            if isinstance(value, str):
                event_dict[key] = _mask_value(value)
    return event_dict


def configure_logging(
    level: int = logging.INFO,
    mask_pii: bool = False,
    json_output: bool = True,
) -> None:
    """Configure structlog and stdlib logging for JSON structured output."""
    global _MASK_PII
    _MASK_PII = mask_pii

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _redact_secrets,
        _mask_pii,
    ]

    if json_output:
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)


def get_logger(component: str) -> structlog.stdlib.BoundLogger:
    """Return a logger bound with the component name."""
    return structlog.get_logger(component=component)


def bind_context(**kwargs: Any) -> None:
    """Bind request-scoped context values for subsequent log entries."""
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_context() -> None:
    """Clear request-scoped context values."""
    structlog.contextvars.clear_contextvars()


def render_event_dict(event_dict: dict[str, Any]) -> str:
    """Render an event dictionary as JSON for testing."""
    processed = _mask_pii(None, "", _redact_secrets(None, "", dict(event_dict)))
    rendered = structlog.processors.JSONRenderer()(None, "", processed)
    if isinstance(rendered, bytes):
        return rendered.decode("utf-8")
    return rendered


def parse_json_log_line(line: str) -> dict[str, Any]:
    """Parse a JSON log line emitted by structlog."""
    return json.loads(line)
