"""Correlation IDs (BE-0.5, Tech Arch §6.2).

An inbound ``X-Correlation-ID`` is accepted only if it matches ``[A-Za-z0-9-]{1,64}``
(which every canonical UUID does). Anything else, or a missing header, is replaced with a
new UUID4. The ID is stored in a contextvar for logs and audit events, and echoed in the
response header.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from contextvars import ContextVar

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

CORRELATION_HEADER = "X-Correlation-ID"
_VALID_CORRELATION_ID = re.compile(r"[A-Za-z0-9-]{1,64}")

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)

request_logger = logging.getLogger("app.request")


def is_valid_correlation_id(value: str | None) -> bool:
    """A canonical UUID always matches the safe charset, so one pattern covers both."""
    return value is not None and _VALID_CORRELATION_ID.fullmatch(value) is not None


def new_correlation_id() -> str:
    return str(uuid.uuid4())


def resolve_correlation_id(value: str | None) -> str:
    return value if is_valid_correlation_id(value) and value is not None else new_correlation_id()


def get_correlation_id() -> str | None:
    return correlation_id_var.get()


class CorrelationIdMiddleware:
    """Pure ASGI middleware so the contextvar is visible to the whole request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        raw = None
        for name, value in scope.get("headers", []):
            if name.lower() == b"x-correlation-id":
                raw = value.decode("latin-1")
                break
        correlation_id = resolve_correlation_id(raw)
        token = correlation_id_var.set(correlation_id)
        status_code = 500
        started = time.perf_counter()

        async def send_with_header(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = MutableHeaders(scope=message)
                headers[CORRELATION_HEADER] = correlation_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            # Method, path and status only: no query string, headers or bodies (§6.2, §9).
            request_logger.info(
                "request completed",
                extra={
                    "http_method": scope.get("method"),
                    "http_path": scope.get("path"),
                    "status_code": status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            correlation_id_var.reset(token)
