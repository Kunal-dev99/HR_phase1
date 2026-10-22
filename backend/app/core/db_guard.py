"""DB-copy guard (D-03, D-16; BE-0.4, BE-1.8).

In-progress work may only touch a database whose name ends in ``_copy`` or ``_test``.
Anything else (including a URL with no database name) is refused.

For SQLite URLs (D-29) the rule applies to the file stem (``Path(database).stem``), so a
directory named ``..._copy`` does not make a file a copy. An empty path, ``:memory:`` and a
bare ``_copy.db`` are refused.

Shared by the pytest harness (always) and ``alembic/env.py`` (when ``ENVIRONMENT`` is
``development`` or ``test``). Staging and production migrations are not affected.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from app.core.settings import Environment

ALLOWED_SUFFIXES: tuple[str, ...] = ("_copy", "_test")
GUARDED_ENVIRONMENTS: frozenset[Environment] = frozenset(
    {Environment.DEVELOPMENT, Environment.TEST}
)


class UnsafeDatabaseError(RuntimeError):
    """The configured database is not a copy; the operation refuses to run against it."""


# Name kept for the Phase 0 imports (D-01: additive).
UnsafeTestDatabaseError = UnsafeDatabaseError


def assert_copy_database(url: str) -> str:
    """Return the database name if it is a copy, otherwise raise ``UnsafeDatabaseError``."""
    try:
        parsed = make_url(url)
    except ArgumentError as exc:
        raise UnsafeDatabaseError("DATABASE_URL is not a valid database URL") from exc
    name = parsed.database or ""
    if parsed.get_backend_name() == "sqlite":
        stem = "" if name in ("", ":memory:") else Path(name).stem
        if not stem.endswith(ALLOWED_SUFFIXES) or stem in ALLOWED_SUFFIXES:
            raise UnsafeDatabaseError(
                f"Refusing to use SQLite database {name!r}: the file name must end in "
                f"{' or '.join(ALLOWED_SUFFIXES)} before the extension (D-03, D-29)."
            )
        return name
    if not name or not name.endswith(ALLOWED_SUFFIXES) or name in ALLOWED_SUFFIXES:
        raise UnsafeDatabaseError(
            f"Refusing to use database {name!r}: the name must end in "
            f"{' or '.join(ALLOWED_SUFFIXES)} (D-03)."
        )
    return name


def guard_database_for_environment(url: str, environment: Environment) -> None:
    """Apply the copy rule in development and test; staging and production pass through."""
    if environment in GUARDED_ENVIRONMENTS:
        assert_copy_database(url)
