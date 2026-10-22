"""Async Alembic environment (BE-0.3). Reads DATABASE_URL from app settings.

BE-1.8 (D-16): when ``ENVIRONMENT`` is ``development`` or ``test``, the database must be a
copy (name ending in ``_copy`` or ``_test``). The check runs before any connection is
opened; a refusal prints the rejected database name and exits non-zero.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from alembic.util import CommandError
from sqlalchemy import pool
from sqlalchemy.engine import Connection

from app.core.db import Base, make_engine
from app.core.db_guard import UnsafeDatabaseError, guard_database_for_environment
from app.core.settings import get_settings

# Every module's models are imported so Base.metadata is complete (autogenerate support).
from app.modules.audit import models as audit_models  # noqa: F401
from app.modules.integrations import models as integrations_models  # noqa: F401
from app.modules.requisitions import models as requisitions_models  # noqa: F401
from app.modules.role_briefs import models as role_briefs_models  # noqa: F401

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    """The target URL, refused before connecting if it is not a copy (D-03, D-16)."""
    url = config.attributes.get("database_url")
    resolved = str(url) if url else get_settings().DATABASE_URL
    try:
        guard_database_for_environment(resolved, get_settings().ENVIRONMENT)
    except UnsafeDatabaseError as exc:
        raise CommandError(str(exc)) from None
    return resolved


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_sync_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    url = _database_url()  # guarded before the engine exists
    engine = make_engine(url, poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run_sync_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
