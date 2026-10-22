"""Async database access (BE-0.3).

One ``AsyncSession`` per unit of work: ``get_session`` opens a transaction, commits it when
the request handler returns normally and rolls it back on any exception. Repositories use
the session; they never commit on their own.

Phase 5 (D-28, D-29): ``make_engine`` builds every engine (app, Alembic, tests) and adds the
SQLite connection setup; ``JSONType``, ``StringList`` and ``UTCDateTime`` are column types
that map to JSONB / ARRAY / timestamptz on PostgreSQL and to portable types on SQLite.
"""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Dialect, MetaData, String, event
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.engine import make_url
from sqlalchemy.ext import asyncio as sa_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator, TypeEngine

from app.core.settings import get_settings

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# --- Portable column types (D-28) -------------------------------------------------------

#: JSON everywhere; JSONB on PostgreSQL (DDL unchanged there).
JSONType: TypeEngine[Any] = JSON().with_variant(JSONB(), "postgresql")


def StringList(length: int) -> TypeEngine[Any]:  # noqa: N802 - used like a type
    """A list of strings: JSON array on SQLite, ``varchar(length)[]`` on PostgreSQL."""
    return JSON().with_variant(ARRAY(String(length)), "postgresql")


def utc_now() -> datetime:
    """The app clock (D-28): timezone-aware UTC."""
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """``timestamptz`` that always binds and returns aware UTC (SQLite returns naive)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


# --- Engine factory (D-29) ---------------------------------------------------------------

SQLITE_BUSY_TIMEOUT_SECONDS = 15

# sa.Uuid stores UUIDs on SQLite as 32-char hex; raw text() binds must match.
sqlite3.register_adapter(uuid.UUID, lambda value: value.hex)


def _install_sqlite_setup(engine: AsyncEngine) -> None:
    """Foreign keys on, and the pysqlite transaction recipe (SAVEPOINTs, transactional DDL)."""

    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_connection: Any, _record: Any) -> None:
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    @event.listens_for(engine.sync_engine, "begin")
    def _on_begin(connection: Any) -> None:
        connection.exec_driver_sql("BEGIN")


def make_engine(url: str, **kwargs: Any) -> AsyncEngine:
    """Build an async engine. PostgreSQL: as before. SQLite: D-29 connection setup.

    ``create_async_engine`` is looked up on its module at call time, so the Alembic guard
    test can still intercept engine creation (BE-1.8).
    """
    create_async_engine = sa_asyncio.create_async_engine
    if make_url(url).get_backend_name() == "sqlite":
        connect_args = dict(kwargs.pop("connect_args", {}))
        connect_args.setdefault("timeout", SQLITE_BUSY_TIMEOUT_SECONDS)
        engine = create_async_engine(url, connect_args=connect_args, **kwargs)
        _install_sqlite_setup(engine)
        return engine
    kwargs.setdefault("pool_pre_ping", True)
    return create_async_engine(url, **kwargs)


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def database_name(url: str) -> str:
    """Return the database name in a SQLAlchemy URL (empty string if none)."""
    return make_url(url).database or ""


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = make_engine(get_settings().DATABASE_URL)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session and one transaction per unit of work."""
    async with get_sessionmaker()() as session, session.begin():
        yield session


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
