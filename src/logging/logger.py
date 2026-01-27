"""Structured logging configuration using structlog."""

import logging
import sys
from pathlib import Path

import structlog
from structlog.types import Processor


def setup_logging(
    level: str = "INFO",
    log_format: str = "console",
    log_file: str | None = None,
) -> None:
    """Configure structured logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_format: Output format ("console" for pretty, "json" for structured)
        log_file: Optional file path for log output
    """
    # Set up standard logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
    )

    # Configure processors based on format
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if log_format == "json":
        # JSON format for production
        processors: list[Processor] = [
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Pretty console format for development
        processors = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(
                colors=True,
                exception_formatter=structlog.dev.plain_traceback,
            ),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Set up file handler if specified
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(getattr(logging, level.upper()))

        # Use JSON format for file logging
        file_formatter = logging.Formatter(
            '{"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}'
        )
        file_handler.setFormatter(file_formatter)

        logging.getLogger().addHandler(file_handler)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a logger instance.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)


# Convenience loggers for common use cases
class LogContext:
    """Context manager for adding temporary context to logs."""

    def __init__(self, **kwargs: str | int | float | bool) -> None:
        self.context = kwargs

    def __enter__(self) -> "LogContext":
        structlog.contextvars.bind_contextvars(**self.context)
        return self

    def __exit__(self, *args: object) -> None:
        structlog.contextvars.unbind_contextvars(*self.context.keys())


def log_adapter_run(
    source_id: str,
    source_name: str,
    ccaa: str,
) -> LogContext:
    """Context manager for logging adapter runs."""
    return LogContext(
        source_id=source_id,
        source_name=source_name,
        ccaa=ccaa,
    )
