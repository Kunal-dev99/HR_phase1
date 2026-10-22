"""Structured JSON logging (BE-0.5, Tech Arch §6.2, §9).

* Every record carries the current correlation ID.
* ``SafeLogFilter`` redacts request/response bodies and payload-like attributes.
* ``JsonFormatter`` emits only a fixed allowlist of fields, so unexpected ``extra``
  attributes (which might hold personal data) never reach the log output.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from app.core.correlation import get_correlation_id

REDACTED = "[redacted]"

# Attributes that may carry request/response content. Never logged.
BODY_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "body",
        "request_body",
        "response_body",
        "content",
        "payload",
        "raw_payload",
        "data",
        "json",
        "form",
        "headers",
        "cookies",
        "query_string",
    }
)

# Extra attributes that are safe to emit.
SAFE_EXTRA_FIELDS: tuple[str, ...] = (
    "http_method",
    "http_path",
    "status_code",
    "duration_ms",
    "event",
    "screening_run_id",
    "requisition_id",
)

HANDLER_NAME = "app-json"


class CorrelationIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "correlation_id"):
            record.correlation_id = get_correlation_id()
        return True


class SafeLogFilter(logging.Filter):
    """Keep request and response bodies out of logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        for attribute in BODY_ATTRIBUTES:
            if attribute in record.__dict__:
                setattr(record, attribute, REDACTED)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", None),
        }
        for field in SAFE_EXTRA_FIELDS:
            if field in record.__dict__:
                entry[field] = record.__dict__[field]
        if record.exc_info and record.exc_info[0] is not None:
            # The exception type only; messages and tracebacks can echo input data.
            entry["exc_type"] = record.exc_info[0].__name__
        return json.dumps(entry, default=str, separators=(",", ":"))


def build_handler() -> logging.Handler:
    handler = logging.StreamHandler()
    handler.set_name(HANDLER_NAME)
    handler.addFilter(CorrelationIdFilter())
    handler.addFilter(SafeLogFilter())
    handler.setFormatter(JsonFormatter())
    return handler


def configure_logging(level: int = logging.INFO) -> None:
    """Attach the JSON handler to the ``app`` logger once (idempotent)."""
    logger = logging.getLogger("app")
    if not any(h.get_name() == HANDLER_NAME for h in logger.handlers):
        logger.addHandler(build_handler())
    logger.setLevel(level)
