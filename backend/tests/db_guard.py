"""Re-export of the DB-copy guard, which now lives in ``app/core/db_guard.py`` (BE-1.8).

Kept so existing test imports keep working (D-01).
"""

from app.core.db_guard import (
    ALLOWED_SUFFIXES,
    UnsafeDatabaseError,
    UnsafeTestDatabaseError,
    assert_copy_database,
)

__all__ = [
    "ALLOWED_SUFFIXES",
    "UnsafeDatabaseError",
    "UnsafeTestDatabaseError",
    "assert_copy_database",
]
