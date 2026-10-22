"""FastAPI application factory (BE-0.2).

``uvicorn app.main:app`` (see ``scripts/start-backend.sh``) serves the module-level ``app``.
Tests build their own instance with ``create_app(settings)``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.correlation import CorrelationIdMiddleware
from app.core.db import dispose_engine, get_sessionmaker
from app.core.logging import configure_logging
from app.core.security import build_principal_provider, ensure_routes_protected
from app.core.settings import Settings, ensure_safe_configuration, get_settings
from app.modules.integrations.service import build_hr_system_adapter
from app.modules.requisitions.router import router as screening_runs_router
from app.modules.requisitions.service import (
    RunExecutor,
    RunRecoveryService,
    build_ingestion_handler,
    build_run_executor,
)

API_V1_PREFIX = "/api/v1"

health_router = APIRouter(tags=["health"])


@health_router.get("/healthz", include_in_schema=True)
async def healthz() -> dict[str, str]:
    """Liveness probe. Public by design: listed in ``PUBLIC_ROUTES``."""
    return {"status": "ok"}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    executor: RunExecutor | None = getattr(app.state, "run_executor", None)
    if settings.FEATURE_SCREENING_RUNS and executor is not None:
        # Startup recovery (D-06): only when the feature is on.
        async with get_sessionmaker()() as session:
            await RunRecoveryService(session).recover(executor)
    yield
    if executor is not None:
        await executor.shutdown()
    await dispose_engine()


def _session_scope() -> AsyncSession:
    return get_sessionmaker()()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    # Validated again here in case a Settings object was built without validation.
    ensure_safe_configuration(settings)

    app = FastAPI(
        title="AI-Enabled Recruitment Screening System",
        version="0.1.0",
        # Interactive docs and the OpenAPI route are not mounted: they would be public
        # routes outside PUBLIC_ROUTES (D-08). The schema stays available via app.openapi().
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    configure_logging()
    app.state.settings = settings
    app.state.principal_provider = build_principal_provider(settings)
    app.add_middleware(CorrelationIdMiddleware)
    app.include_router(health_router)
    # Screening-run routes and execution exist only when the feature is on (D-11, D-02).
    if settings.FEATURE_SCREENING_RUNS:
        adapter = build_hr_system_adapter(settings)  # unset or unknown adapter: refuse
        app.state.hr_system_key = adapter.hr_system_key
        app.state.run_executor = build_run_executor(
            settings, build_ingestion_handler(settings, adapter, _session_scope)
        )
        app.include_router(screening_runs_router, prefix=API_V1_PREFIX)

    # Fail closed (D-04): refuse to start if any non-public route lacks a permission.
    ensure_routes_protected(app)
    return app


app = create_app()
