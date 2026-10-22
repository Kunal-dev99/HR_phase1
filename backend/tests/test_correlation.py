import json
import logging
import uuid

import pytest
from httpx import AsyncClient

from app.core.correlation import CORRELATION_HEADER, is_valid_correlation_id
from app.core.logging import JsonFormatter, SafeLogFilter, build_handler


def _is_uuid4(value: str) -> bool:
    try:
        return uuid.UUID(value).version == 4
    except ValueError:
        return False


async def test_echoes_valid_and_replaces_invalid_correlation_id(client: AsyncClient) -> None:
    valid_uuid = str(uuid.uuid4())
    for valid in (valid_uuid, valid_uuid.upper(), "abc-123", "A" * 64):
        response = await client.get("/healthz", headers={CORRELATION_HEADER: valid})
        assert response.status_code == 200
        assert response.headers[CORRELATION_HEADER] == valid

    for invalid in ("", "a" * 65, "bad id", "abc_123", "x;drop", "{" + valid_uuid + "}", "é"):
        response = await client.get(
            "/healthz", headers={CORRELATION_HEADER: invalid.encode("utf-8")}
        )
        echoed = response.headers[CORRELATION_HEADER]
        assert echoed != invalid
        assert _is_uuid4(echoed)

    response = await client.get("/healthz")
    assert _is_uuid4(response.headers[CORRELATION_HEADER])

    # Each request without a valid ID gets a fresh one.
    first = (await client.get("/healthz")).headers[CORRELATION_HEADER]
    second = (await client.get("/healthz")).headers[CORRELATION_HEADER]
    assert first != second


def test_validator_rules() -> None:
    assert is_valid_correlation_id("a")
    assert is_valid_correlation_id(str(uuid.uuid4()))
    assert not is_valid_correlation_id(None)
    assert not is_valid_correlation_id("")
    assert not is_valid_correlation_id("a" * 65)


async def test_request_log_is_json_with_correlation_id_and_no_body(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    formatter = JsonFormatter()
    handler = build_handler()
    with caplog.at_level(logging.INFO, logger="app.request"):
        response = await client.post(
            "/healthz?email=jane@example.com",
            headers={CORRELATION_HEADER: "corr-1"},
            content=b'{"cv": "Jane Doe, jane@example.com"}',
        )
    assert response.status_code == 405
    records = [r for r in caplog.records if r.name == "app.request"]
    assert records
    for record in records:
        for log_filter in handler.filters:
            assert isinstance(log_filter, logging.Filter)
            log_filter.filter(record)
        line = formatter.format(record)
        entry = json.loads(line)
        assert entry["correlation_id"] == "corr-1"
        assert entry["http_path"] == "/healthz"
        assert "jane" not in line.lower()


def test_safe_filter_redacts_bodies() -> None:
    record = logging.LogRecord("app.x", logging.INFO, __file__, 1, "msg", None, None)
    record.body = "secret cv text"
    record.response_body = "secret"
    record.unknown_extra = "maybe pii"
    SafeLogFilter().filter(record)
    assert record.body == "[redacted]"
    assert record.response_body == "[redacted]"
    line = JsonFormatter().format(record)
    assert "secret" not in line
    assert "maybe pii" not in line
