"""Write the backend OpenAPI schema to ``backend/openapi.json`` (BE-3.1, D-23).

Usage (from ``backend/``)::

    python scripts/export_openapi.py

The app is built with feature-flagged routes switched on so they appear in the schema.
The lifespan is not run and no database connection is opened: the ``DATABASE_URL`` is a
placeholder and the engine is created lazily. No route is mounted (D-14 is unchanged).
Offline tooling only; the application never imports this module.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
OUTPUT_PATH = BACKEND_DIR / "openapi.json"
PLACEHOLDER_DATABASE_URL = "postgresql+asyncpg://placeholder@localhost:5432/placeholder"

# Pinned so the export never depends on a developer's backend/.env or shell environment.
EXPORT_ENVIRONMENT: dict[str, str] = {
    "DATABASE_URL": PLACEHOLDER_DATABASE_URL,
    "ENVIRONMENT": "development",
    "AUTH_MODE": "disabled",
    "FEATURE_SCREENING_RUNS": "true",
    "HR_SYSTEM_ADAPTER": "mock",
}


def build_schema() -> dict[str, Any]:
    # Environment variables take precedence over backend/.env, so importing app.main
    # (which builds a module-level app) also uses the placeholder values.
    os.environ.update(EXPORT_ENVIRONMENT)
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    settings_module = importlib.import_module("app.core.settings")
    main_module = importlib.import_module("app.main")
    settings = settings_module.Settings(
        DATABASE_URL=PLACEHOLDER_DATABASE_URL,
        ENVIRONMENT=settings_module.Environment.DEVELOPMENT,
        FEATURE_SCREENING_RUNS=True,
        HR_SYSTEM_ADAPTER=settings_module.MOCK_HR_SYSTEM_ADAPTER,
    )
    app = main_module.create_app(settings)
    schema: dict[str, Any] = app.openapi()
    return schema


def main() -> int:
    schema = build_schema()
    OUTPUT_PATH.write_text(
        json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT_PATH} ({len(schema.get('paths', {}))} paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
