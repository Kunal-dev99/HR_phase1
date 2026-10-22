"""Migration round trip (BE-0.4). Every migration task relies on this test (D-02)."""

import asyncio

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from tests.conftest import alembic_config


async def _current_revision(url: str) -> str | None:
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            exists = await conn.scalar(text("SELECT to_regclass('public.alembic_version')"))
            if exists is None:
                return None
            return await conn.scalar(text("SELECT version_num FROM alembic_version"))
    finally:
        await engine.dispose()


async def _public_tables(url: str) -> set[str]:
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            rows = await conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
            return {r[0] for r in rows} - {"alembic_version"}
    finally:
        await engine.dispose()


PHASE1_TABLES = {
    "requisition",
    "requisition_snapshot",
    "requisition_snapshot_payload",
    "screening_run",
    "integration_attempt",
}


@pytest.mark.pg_only
def test_migration_round_trip(migrated_database: str) -> None:
    cfg = alembic_config()
    head = ScriptDirectory.from_config(cfg).get_current_head()

    assert asyncio.run(_current_revision(migrated_database)) == head
    tables_at_head = asyncio.run(_public_tables(migrated_database))
    assert PHASE1_TABLES | {"audit_event"} <= tables_at_head

    command.downgrade(cfg, "base")
    assert asyncio.run(_current_revision(migrated_database)) is None
    assert asyncio.run(_public_tables(migrated_database)) == set()

    command.upgrade(cfg, "head")
    assert asyncio.run(_current_revision(migrated_database)) == head
    assert asyncio.run(_public_tables(migrated_database)) == tables_at_head


@pytest.mark.pg_only
def test_downgrade_0002_removes_only_its_tables(migrated_database: str) -> None:
    cfg = alembic_config()
    try:
        command.downgrade(cfg, "0001_audit_event")
        assert asyncio.run(_current_revision(migrated_database)) == "0001_audit_event"
        assert asyncio.run(_public_tables(migrated_database)) == {"audit_event"}
    finally:
        command.upgrade(cfg, "head")
    assert PHASE1_TABLES <= asyncio.run(_public_tables(migrated_database))
