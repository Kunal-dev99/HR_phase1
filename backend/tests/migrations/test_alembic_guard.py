"""Alembic CLI DB-copy guard (BE-1.8, D-16)."""

from collections.abc import Iterator
from typing import Any

import pytest
import sqlalchemy.ext.asyncio
from alembic import command
from alembic.config import Config
from alembic.util import CommandError

from app.core.settings import get_settings
from tests.conftest import BACKEND_DIR

# Port 1 on loopback: if anything did try to connect, it would fail loudly, not hang.
NON_COPY_URL = "postgresql+asyncpg://u:p@127.0.0.1:1/hr_phase1"


class _ConnectionAttemptedError(AssertionError):
    pass


@pytest.fixture
def engine_calls(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Record (and refuse) every engine creation made by alembic/env.py."""
    calls: list[str] = []

    def fake_create_async_engine(url: Any, *args: Any, **kwargs: Any) -> Any:
        calls.append(str(url))
        raise _ConnectionAttemptedError("alembic tried to open a connection")

    # env.py is executed afresh by every command and imports the name at that time.
    monkeypatch.setattr(sqlalchemy.ext.asyncio, "create_async_engine", fake_create_async_engine)
    yield calls


def _cli_config(monkeypatch: pytest.MonkeyPatch, environment: str) -> Config:
    """A config like the CLI's: no URL override, so env.py reads settings (env vars win)."""
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv("DATABASE_URL", NON_COPY_URL)
    get_settings.cache_clear()
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(autouse=True)
def _restore_settings() -> Iterator[None]:
    yield
    get_settings.cache_clear()  # later tests see the real backend/.env settings again


def test_alembic_refuses_non_copy_database_in_development(
    monkeypatch: pytest.MonkeyPatch, engine_calls: list[str]
) -> None:
    for environment in ("development", "test"):
        cfg = _cli_config(monkeypatch, environment)
        assert get_settings().DATABASE_URL == NON_COPY_URL
        calls: list[tuple[Any, tuple[Any, ...], dict[str, Any]]] = [
            (command.current, (cfg,), {}),
            (command.upgrade, (cfg, "head"), {}),
            (command.downgrade, (cfg, "base"), {}),
            (command.upgrade, (cfg, "head"), {"sql": True}),  # offline mode too
        ]
        for func, args, kwargs in calls:
            with pytest.raises(CommandError, match=r"Refusing to use database 'hr_phase1'"):
                func(*args, **kwargs)
    assert engine_calls == []  # refused before any connection was attempted

    # Staging and production are not affected: env.py goes on to create the engine.
    for environment in ("staging", "production"):
        cfg = _cli_config(monkeypatch, environment)
        with pytest.raises(_ConnectionAttemptedError):
            command.current(cfg)
    assert engine_calls == [NON_COPY_URL, NON_COPY_URL]


def test_guard_moved_to_core_and_reexported() -> None:
    import app.core.db_guard as core
    import tests.db_guard as legacy

    assert legacy.assert_copy_database is core.assert_copy_database
    assert legacy.UnsafeTestDatabaseError is core.UnsafeDatabaseError
