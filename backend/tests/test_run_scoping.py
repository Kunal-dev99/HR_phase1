"""Row scoping and single-winner claim for screening runs (BE-1.3, D-04, D-06, D-09)."""

import asyncio
import inspect
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.security import Principal
from app.modules.requisitions.constants import RunStatus
from app.modules.requisitions.repository import ScreeningRunRepository

APP_DIR = Path(__file__).resolve().parents[1] / "app"


def _principal(pid: str, *units: str) -> Principal:
    return Principal(
        id=pid,
        permissions=frozenset({"screening_run:read"}),
        business_units=frozenset(units),
    )


async def _run(
    repo: ScreeningRunRepository, started_by: str, business_unit_key: str | None
) -> uuid.UUID:
    run = await repo.add(
        hr_system_key="mock",
        external_requisition_id="REQ-SCOPE-1",
        started_by=started_by,
        scope_business_units=["bu-1"],
        correlation_id="corr-scope",
    )
    if business_unit_key is not None:
        await repo.transition(
            run.id,
            expected_status=RunStatus.CREATED,
            new_status=RunStatus.CREATED,
            business_unit_key=business_unit_key,
        )
    return run.id


async def test_principal_cannot_read_other_business_unit_run(db_session: AsyncSession) -> None:
    repo = ScreeningRunRepository(db_session)
    bu1_run = await _run(repo, "alice", "bu-1")
    bu2_run = await _run(repo, "alice", "bu-2")
    unresolved = await _run(repo, "alice", None)

    async def visible(principal: Principal) -> set[uuid.UUID]:
        found = set()
        for run_id in (bu1_run, bu2_run, unresolved):
            if await repo.get_for_principal(run_id, principal) is not None:
                found.add(run_id)
        return found

    # Business-unit membership decides visibility of resolved runs.
    assert await visible(_principal("bob", "bu-1")) == {bu1_run}
    assert await visible(_principal("carol", "bu-2")) == {bu2_run}
    assert await visible(_principal("dave", "bu-other")) == set()
    assert await visible(_principal("erin")) == set()

    # The starter sees their own unresolved run (business_unit_key IS NULL), even with
    # no business unit matching; nobody else does.
    assert await visible(_principal("alice", "bu-other")) == {unresolved}
    assert await visible(_principal("alice", "bu-1")) == {bu1_run, unresolved}

    # The wildcard is honoured only when explicitly granted, and only for resolved runs.
    assert await visible(_principal("root", "*")) == {bu1_run, bu2_run}
    assert await visible(_principal("root", "bu-*")) == set()

    # Missing and out-of-scope are indistinguishable (both None).
    assert await repo.get_for_principal(uuid.uuid4(), _principal("bob", "bu-1")) is None

    # The scoped read takes no business-unit argument a caller could widen (D-04).
    params = set(inspect.signature(ScreeningRunRepository.get_for_principal).parameters)
    assert params == {"self", "run_id", "principal"}

    # The workflow read is unscoped and is not used by any router.
    assert await repo.get_for_workflow(bu2_run) is not None
    for router in APP_DIR.glob("modules/*/router.py"):
        source = router.read_text()
        assert "get_for_workflow" not in source, router
        assert ".repository" not in source, router


@pytest_asyncio.fixture
async def committed_run(migrated_database: str) -> AsyncIterator[tuple[str, uuid.UUID]]:
    """A run committed for real, so two connections can race for it. Removed afterwards.

    Test-data cleanup on the copy only; screening_run is not append-only and no audit or
    integration rows are written for this run.
    """
    engine = create_async_engine(migrated_database, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session, session.begin():
        run = await ScreeningRunRepository(session).add(
            hr_system_key="mock",
            external_requisition_id="REQ-CLAIM-1",
            started_by="alice",
            scope_business_units=["bu-1"],
            correlation_id="corr-claim",
        )
    try:
        yield migrated_database, run.id
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM screening_run WHERE id = :id"), {"id": run.id})
        await engine.dispose()


async def test_claim_is_single_winner(
    committed_run: tuple[str, uuid.UUID], db_session: AsyncSession
) -> None:
    url, run_id = committed_run
    engine = create_async_engine(url, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as first, sessions() as second:
            winner = await ScreeningRunRepository(first).claim_for_ingestion(run_id)
            assert winner is not None
            assert winner.status == RunStatus.INGESTING_REQUISITION

            # The second claim blocks on the row lock held by the first transaction...
            contender = asyncio.create_task(
                ScreeningRunRepository(second).claim_for_ingestion(run_id)
            )
            await asyncio.sleep(0.3)
            assert not contender.done()

            # ...and once the first commits, the re-checked WHERE status='created' fails.
            await first.commit()
            assert await asyncio.wait_for(contender, timeout=5) is None
            await second.commit()

        async with sessions() as check:
            run = await ScreeningRunRepository(check).get_for_workflow(run_id)
            assert run is not None
            assert run.status == RunStatus.INGESTING_REQUISITION
    finally:
        await engine.dispose()

    # Sequential claims in one transaction: also exactly one winner.
    repo = ScreeningRunRepository(db_session)
    local = await repo.add(
        hr_system_key="mock",
        external_requisition_id="REQ-CLAIM-2",
        started_by="alice",
        scope_business_units=["bu-1"],
        correlation_id="corr-claim-2",
    )
    results = [await repo.claim_for_ingestion(local.id) for _ in range(3)]
    assert [r is not None for r in results] == [True, False, False]
    assert await repo.claim_for_ingestion(uuid.uuid4()) is None
