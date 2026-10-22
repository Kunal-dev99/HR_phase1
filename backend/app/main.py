"""FastAPI application factory (BE-0.2).

``uvicorn app.main:app`` (see ``scripts/start-backend.sh``) serves the module-level ``app``.
Tests build their own instance with ``create_app(settings)``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from app.core.correlation import CorrelationIdMiddleware
from app.core.db import dispose_engine
from app.core.logging import configure_logging
from app.core.security import build_principal_provider, ensure_routes_protected
from app.core.settings import Settings, ensure_safe_configuration, get_settings

API_V1_PREFIX = "/api/v1"

health_router = APIRouter(tags=["health"])


@health_router.get("/healthz", include_in_schema=True)
async def healthz() -> dict[str, str]:
    """Liveness probe. Public by design: listed in ``PUBLIC_ROUTES``."""
    return {"status": "ok"}


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


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
    # Feature routers are mounted here; screening-run routes only when
    # settings.FEATURE_SCREENING_RUNS is true (D-11, Phase 2).

    # Fail closed (D-04): refuse to start if any non-public route lacks a permission.
    ensure_routes_protected(app)
    return app


app = create_app()
