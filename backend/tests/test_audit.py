import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.correlation import correlation_id_var
from app.modules.audit.constants import ActorType
from app.modules.audit.repository import AuditRepository
from app.modules.audit.service import AuditService, MissingCorrelationIdError


async def _record(session: AsyncSession, run_id: uuid.UUID) -> uuid.UUID:
    event = await AuditService.for_session(session).record(
        screening_run_id=run_id,
        entity_type="screening_run",
        entity_id=str(run_id),
        event_type="ScreeningRunCreated",
        actor_type=ActorType.USER,
        actor_id="user-1",
        correlation_id="corr-audit-1",
        details={"external_requisition_id": "REQ-1"},
    )
    return event.id


@pytest.mark.pg_only
async def test_audit_event_is_append_only(db_session: AsyncSession) -> None:
    run_id = uuid.uuid4()
    event_id = await _record(db_session, run_id)

    with pytest.raises(DBAPIError, match="append-only"):
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE audit_event SET reason_code = 'tampered' WHERE id = :id"),
                {"id": event_id},
            )

    with pytest.raises(DBAPIError, match="append-only"):
        async with db_session.begin_nested():
            await db_session.execute(
                text("DELETE FROM audit_event WHERE id = :id"), {"id": event_id}
            )

    with pytest.raises(DBAPIError, match="append-only"):
        async with db_session.begin_nested():
            await db_session.execute(text("TRUNCATE audit_event"))

    # The row is still there and unchanged.
    row = (
        await db_session.execute(
            text("SELECT reason_code, correlation_id FROM audit_event WHERE id = :id"),
            {"id": event_id},
        )
    ).one()
    assert row.reason_code is None
    assert row.correlation_id == "corr-audit-1"

    # The repository offers no mutation path.
    assert not any(
        name.startswith(("update", "delete", "remove")) for name in dir(AuditRepository)
    )


async def test_record_joins_caller_transaction(db_session: AsyncSession) -> None:
    run_id = uuid.uuid4()
    async with db_session.begin_nested() as unit_of_work:
        await _record(db_session, run_id)
        await unit_of_work.rollback()
    assert await AuditService.for_session(db_session).list_for_run(run_id) == []

    await _record(db_session, run_id)
    events = await AuditService.for_session(db_session).list_for_run(run_id)
    assert len(events) == 1
    event = events[0]
    assert event.actor_type is ActorType.USER
    assert event.details == {"external_requisition_id": "REQ-1"}
    assert event.timestamp is not None


async def test_record_uses_context_correlation_id_or_refuses(db_session: AsyncSession) -> None:
    service = AuditService.for_session(db_session)
    run_id = uuid.uuid4()
    token = correlation_id_var.set("ctx-corr-1")
    try:
        event = await service.record(
            screening_run_id=run_id,
            entity_type="screening_run",
            entity_id=str(run_id),
            event_type="RunStatusChanged",
            actor_type=ActorType.SYSTEM,
            actor_id="requisitions.ingestion",
        )
    finally:
        correlation_id_var.reset(token)
    assert event.correlation_id == "ctx-corr-1"

    with pytest.raises(MissingCorrelationIdError):
        await service.record(
            screening_run_id=run_id,
            entity_type="screening_run",
            entity_id=str(run_id),
            event_type="RunStatusChanged",
            actor_type=ActorType.SYSTEM,
        )


async def test_details_must_be_small(db_session: AsyncSession) -> None:
    service = AuditService.for_session(db_session)
    with pytest.raises(ValidationError):
        await service.record(
            screening_run_id=uuid.uuid4(),
            entity_type="screening_run",
            entity_id="x",
            event_type="RunStatusChanged",
            actor_type=ActorType.SYSTEM,
            correlation_id="c-1",
            details={"cv_text": "x" * 1000},
        )


async def test_details_key_count_and_key_length_limits(db_session: AsyncSession) -> None:
    """D-15: at most 32 keys, and keys/strings (including list items) at most 256 chars."""
    service = AuditService.for_session(db_session)

    async def record(details: dict[str, object]) -> None:
        await service.record(
            screening_run_id=uuid.uuid4(),
            entity_type="screening_run",
            entity_id="x",
            event_type="RunStatusChanged",
            actor_type=ActorType.SYSTEM,
            correlation_id="c-1",
            details=details,  # type: ignore[arg-type]
        )

    await record({f"k{i}": i for i in range(32)})  # exactly at the limit
    await record({"k" * 256: "v" * 256, "items": ["x" * 256]})
    for too_much in (
        {f"k{i}": i for i in range(33)},
        {"k" * 257: 1},
        {"items": ["ok", "x" * 257]},
    ):
        with pytest.raises(ValidationError):
            await record(too_much)
