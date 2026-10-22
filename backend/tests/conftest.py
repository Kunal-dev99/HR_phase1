"""Test harness (BE-0.4).

* Refuses to run unless DATABASE_URL names a database copy (``*_copy`` / ``*_test``).
* Migrates the copy to head once per session.
* Gives every test its own connection wrapped in a transaction that is rolled back, so no
  test leaves data behind. Code under test that "commits" only releases a savepoint.
* Provides an httpx ``AsyncClient`` bound to an app whose session dependency uses that
  rolled-back transaction.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.db import get_session
from app.core.settings import Settings, get_settings
from app.main import create_app
from app.modules.integrations.adapters.hr_system.mock import MockHRSystemAdapter
from app.modules.requisitions.service import InlineExecutor, build_ingestion_handler
from tests.db_guard import UnsafeTestDatabaseError, assert_copy_database

BACKEND_DIR = Path(__file__).resolve().parents[1]


def pytest_configure(config: pytest.Config) -> None:
    try:
        assert_copy_database(get_settings().DATABASE_URL)
    except UnsafeTestDatabaseError as exc:
        raise pytest.UsageError(str(exc)) from exc


def alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["configure_logger"] = False
    cfg.attributes["database_url"] = database_url()
    return cfg


def database_url() -> str:
    url = get_settings().DATABASE_URL
    assert_copy_database(url)  # checked again right before any database work
    return url


@pytest.fixture(scope="session")
def migrated_database() -> Iterator[str]:
    """Upgrade the copy to head once per test session."""
    url = database_url()
    command.upgrade(alembic_config(), "head")
    yield url


@pytest_asyncio.fixture
async def db_connection(migrated_database: str) -> AsyncIterator[AsyncConnection]:
    engine = create_async_engine(migrated_database, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                yield connection
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_connection: AsyncConnection) -> AsyncIterator[AsyncSession]:
    session = AsyncSession(
        bind=db_connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    try:
        yield session
    finally:
        await session.close()


@pytest.fixture
def test_settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        ENVIRONMENT="test",
        DATABASE_URL=database_url(),
    )


@pytest.fixture
def app(test_settings: Settings) -> FastAPI:
    return create_app(test_settings)


@pytest_asyncio.fixture
async def client(app: FastAPI, db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _session_override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def screening_settings() -> Settings:
    """Feature on, dev-header auth, mock HR System, inline executor (BE-2.3-2.5)."""
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        ENVIRONMENT="test",
        DATABASE_URL=database_url(),
        AUTH_MODE="dev_header",
        FEATURE_SCREENING_RUNS=True,
        HR_SYSTEM_ADAPTER="mock",
        RUN_EXECUTOR="inline",
    )


@pytest_asyncio.fixture
async def screening_client(
    screening_settings: Settings, db_session: AsyncSession
) -> AsyncIterator[AsyncClient]:
    """Client whose requests and inline ingestion share the rolled-back test session."""
    app = create_app(screening_settings)

    @asynccontextmanager
    async def _scope() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.state.run_executor = InlineExecutor(
        build_ingestion_handler(screening_settings, MockHRSystemAdapter(), _scope)
    )
    app.dependency_overrides[get_session] = _session_override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def dev_headers(
    permissions: str = "screening_run:create,screening_run:read",
    business_units: str = "bu-1",
    principal_id: str = "recruiter-1",
) -> dict[str, str]:
    return {
        "X-Dev-Principal-Id": principal_id,
        "X-Dev-Permissions": permissions,
        "X-Dev-Business-Units": business_units,
    }
