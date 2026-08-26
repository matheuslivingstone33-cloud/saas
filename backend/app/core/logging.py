"""Log estruturado (JSON) com contexto de request/provedor/custo."""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import structlog

_configured = False


def nivel_padrao() -> str:
    """LOG_LEVEL manda; em APP_ENV=test o padrao e WARNING (suite silenciosa)."""
    explicito = os.environ.get("LOG_LEVEL")
    if explicito:
        return explicito.upper()
    return "WARNING" if os.environ.get("APP_ENV") == "test" else "INFO"


def configure_logging(level: str | None = None) -> None:
    global _configured
    level = level or nivel_padrao()
    if _configured:
        return
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level, logging.INFO)),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str = "prospector", **initial: Any) -> Any:
    configure_logging()
    return structlog.get_logger(name).bind(**initial)
