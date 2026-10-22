"""Run executor and startup recovery (BE-2.2, D-06)."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.core.settings import Settings
from app.modules.audit.service import AuditService
from app.modules.integrations.adapters.hr_system.mock import MockHRSystemAdapter
from app.modules.requisitions.constants import CompletionReason, RunStatus
from app.modules.requisitions.repository import ScreeningRunRepository
from app.modules.requisitions.service import (
    InlineExecutor,
    InvalidRunRequestError,
    RunRecoveryService,
    ScreeningRunService,
    build_ingestion_handler,
)

STARTER = Principal(
    id="recruiter-1",
    permissions=frozenset({"screening_run:create", "screening_run:read"}),
    business_units=frozenset({"bu-1"}),
)


class RecordingExecutor:
    def __init__(self, log: list[str]) -> None:
        self.log = log
        self.dispatched: list[uuid.UUID] = []

    async def dispatch(self, run_id: uuid.UUID) -> None:
        self.log.append("dispatch")
        self.dispatched.append(run_id)

    async def shutdown(self) -> None:
        return None


def _service(session: AsyncSession) -> ScreeningRunService:
    return ScreeningRunService.for_session(session, hr_system_key="mock")


async def test_dispatch_after_commit_only(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    log: list[str] = []
    real_commit = db_session.commit

    async def recording_commit() -> None:
        await real_commit()
        log.append("commit")

    monkeypatch.setattr(db_session, "commit", recording_commit)
    executor = RecordingExecutor(log)

    run = await _service(db_session).start(STARTER, "REQ-OPEN-1", "corr-exec-1", executor)
    assert log == ["commit", "dispatch"]
    assert executor.dispatched == [run.id]

    # A creation that fails never commits and never dispatches.
    log.clear()
    with pytest.raises(InvalidRunRequestError):
        await _service(db_session).start(STARTER, "   ", "corr-exec-2", executor)
    assert log == []


@pytest.mark.pg_only
async def test_startup_recovery_redispatches_created_and_blocks_stale(
    db_session: AsyncSession,
) -> None:
    service = _service(db_session)
    created = await service.create(STARTER, "REQ-OPEN-1", "corr-rec-1")
    stale = await service.create(STARTER, "REQ-OPEN-1", "corr-rec-2")
    await db_session.commit()
    runs = ScreeningRunRepository(db_session)
    assert await runs.claim_for_ingestion(stale.id) is not None
    await db_session.execute(
        text("UPDATE screening_run SET started_at = now() - interval '1 hour' WHERE id = :id"),
        {"id": stale.id},
    )
    await db_session.commit()

    executor = RecordingExecutor([])
    redispatched, blocked = await RunRecoveryService(db_session).recover(
        executor, stale_after_seconds=600
    )

    assert created.id in redispatched and created.id in executor.dispatched
    assert stale.id in blocked and stale.id not in executor.dispatched
    run = await runs.get_for_workflow(stale.id)
    assert run is not None
    assert run.status == RunStatus.BLOCKED
    assert run.completion_reason == CompletionReason.INGESTION_INTERRUPTED
    assert run.completed_at is not None
    events = await AuditService.for_session(db_session).list_for_run(stale.id)
    assert events[-1].event_type == "RunStatusChanged"
    assert events[-1].reason_code == "ingestion_interrupted"


async def test_double_dispatch_ingests_once(db_session: AsyncSession) -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None, ENVIRONMENT="test", DATABASE_URL="postgresql+asyncpg://x/y_copy"
    )

    @asynccontextmanager
    async def scope() -> AsyncIterator[AsyncSession]:
        yield db_session

    executor = InlineExecutor(build_ingestion_handler(settings, MockHRSystemAdapter(), scope))
    run = await _service(db_session).start(STARTER, "REQ-OPEN-1", "corr-dbl-1", executor)
    await executor.dispatch(run.id)  # second dispatch of the same run

    attempts = await db_session.scalar(
        text("SELECT count(*) FROM integration_attempt WHERE screening_run_id = :id"),
        {"id": run.id},
    )
    assert attempts == 1
    events = await AuditService.for_session(db_session).list_for_run(run.id)
    claims = [e for e in events if e.reason_code == "ingestion_claimed"]
    assert len(claims) == 1
    current = await ScreeningRunRepository(db_session).get_for_workflow(run.id)
    assert current is not None and current.status == RunStatus.ROLE_BRIEF_DRAFT
