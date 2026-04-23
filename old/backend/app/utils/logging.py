"""Structured logging utilities."""

import contextvars
import logging
import sys
import uuid
from typing import Any

import structlog
from structlog.types import EventDict, Processor

from app.config import get_config

# Context variable for correlation ID
correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)


def add_correlation_id(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Add correlation ID to log events."""
    correlation_id = correlation_id_var.get()
    if correlation_id:
        event_dict["correlation_id"] = correlation_id
    return event_dict


def setup_logging() -> None:
    """Configure structured logging for the application."""
    config = get_config()

    # Configure stdlib logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, config.log_level.upper()),
    )

    # Configure structlog
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if config.logging.include_correlation_id:
        processors.append(add_correlation_id)

    processors.extend(
        [
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
        ]
    )

    if config.logging.format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


def set_correlation_id(correlation_id: str | None = None) -> str:
    """Set correlation ID for the current context."""
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())
    correlation_id_var.set(correlation_id)
    return correlation_id


def get_correlation_id() -> str:
    """Get the current correlation ID."""
    return correlation_id_var.get()


def clear_correlation_id() -> None:
    """Clear the correlation ID."""
    correlation_id_var.set("")
