"""DB-copy guard (D-03, BE-0.4).

Tests and test migrations may only touch a database whose name ends in ``_copy`` or
``_test``. Anything else (including a URL with no database name) is refused.
"""

from __future__ import annotations

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

ALLOWED_SUFFIXES: tuple[str, ...] = ("_copy", "_test")


class UnsafeTestDatabaseError(RuntimeError):
    """The configured database is not a copy; tests refuse to run against it."""


def assert_copy_database(url: str) -> str:
    """Return the database name if it is a copy, otherwise raise."""
    try:
        name = make_url(url).database or ""
    except ArgumentError as exc:
        raise UnsafeTestDatabaseError("DATABASE_URL is not a valid database URL") from exc
    if not name or not name.endswith(ALLOWED_SUFFIXES) or name in ALLOWED_SUFFIXES:
        raise UnsafeTestDatabaseError(
            f"Refusing to run tests against database {name!r}: the name must end in "
            f"{' or '.join(ALLOWED_SUFFIXES)} (D-03)."
        )
    return name
