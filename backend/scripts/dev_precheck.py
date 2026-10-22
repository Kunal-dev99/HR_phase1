"""Developer pre-flight checks run by backend-start.bat before the server starts.

Checks, in order, and exits non-zero with a plain message on the first failure:
1. Settings load from backend/.env (plus environment overrides) and pass the
   production-safety validation.
2. DATABASE_URL is a database copy when ENVIRONMENT is development/test (D-03, D-16).
3. PostgreSQL accepts a connection with those credentials.

It never creates, changes or drops anything.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def fail(message: str) -> int:
    print(f"[precheck] FAILED: {message}")
    return 1


async def _ping(dsn: str) -> None:
    import asyncpg  # type: ignore[import-untyped]

    conn = await asyncpg.connect(dsn, timeout=5)
    try:
        await conn.fetchval("SELECT 1")
    finally:
        await conn.close()


def main() -> int:
    from pydantic import ValidationError
    from sqlalchemy.engine import make_url

    from app.core.db_guard import UnsafeDatabaseError, guard_database_for_environment
    from app.core.settings import Settings

    try:
        settings = Settings()  # DATABASE_URL comes from backend/.env or the environment
    except ValidationError as exc:
        return fail(f"backend/.env is invalid or incomplete:\n{exc}")
    except ValueError as exc:
        return fail(f"unsafe configuration: {exc}")

    if "<user>" in settings.DATABASE_URL or "<password>" in settings.DATABASE_URL:
        return fail("DATABASE_URL in backend/.env still has the <user>/<password> placeholders")

    try:
        guard_database_for_environment(settings.DATABASE_URL, settings.ENVIRONMENT)
    except UnsafeDatabaseError as exc:
        return fail(str(exc))

    url = make_url(settings.DATABASE_URL)
    dsn = url.set(drivername="postgresql").render_as_string(hide_password=False)
    try:
        asyncio.run(_ping(dsn))
    except Exception as exc:  # report any connection problem plainly
        return fail(
            f"cannot connect to PostgreSQL at {url.host}:{url.port or 5432}, "
            f"database '{url.database}' as '{url.username}': {type(exc).__name__}: {exc}"
        )

    print(
        f"[precheck] OK: environment={settings.ENVIRONMENT.value}, "
        f"database='{url.database}' on {url.host}:{url.port or 5432}, "
        f"auth_mode={settings.AUTH_MODE.value}, "
        f"screening_runs={'on' if settings.FEATURE_SCREENING_RUNS else 'off'}, "
        f"hr_adapter={settings.HR_SYSTEM_ADAPTER or 'unset'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
