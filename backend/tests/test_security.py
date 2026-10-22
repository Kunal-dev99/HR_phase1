from typing import Annotated

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import iter_route_contexts
from httpx import ASGITransport, AsyncClient
from starlette.routing import Route

from app.core.security import (
    DEV_BUSINESS_UNITS_HEADER,
    DEV_PERMISSIONS_HEADER,
    DEV_PRINCIPAL_ID_HEADER,
    PUBLIC_ROUTES,
    DisabledPrincipalProvider,
    Principal,
    ensure_routes_protected,
    find_unprotected_routes,
    require_permission,
)
from app.core.settings import Settings
from app.main import create_app

URL = "postgresql+asyncpg://u:p@localhost:5432/hr_phase1_p1req_copy"
PROBE = "/api/v1/_probe"


def _app(**overrides: object) -> FastAPI:
    settings = Settings(_env_file=None, DATABASE_URL=URL, **overrides)  # type: ignore[arg-type]
    app = create_app(settings)
    router = APIRouter(prefix="/api/v1")

    @router.get("/_probe")
    async def probe(
        principal: Annotated[Principal, Depends(require_permission("screening_run:read"))],
    ) -> dict[str, object]:
        return {"id": principal.id, "business_units": sorted(principal.business_units)}

    app.include_router(router)
    return app


def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_no_principal_401_missing_permission_403() -> None:
    dev_headers = {
        DEV_PRINCIPAL_ID_HEADER: "user-1",
        DEV_PERMISSIONS_HEADER: "screening_run:read",
        DEV_BUSINESS_UNITS_HEADER: "bu-1",
    }

    # Default AUTH_MODE=disabled: always 401, even with dev headers.
    async with _client(_app()) as client:
        response = await client.get(PROBE, headers=dev_headers)
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"

    async with _client(_app(AUTH_MODE="dev_header")) as client:
        # No principal -> 401.
        assert (await client.get(PROBE)).status_code == 401
        bad_id = {**dev_headers, DEV_PRINCIPAL_ID_HEADER: "bad id!"}
        assert (await client.get(PROBE, headers=bad_id)).status_code == 401

        # Principal without the permission -> 403.
        for permissions in ("", "screening_run:create", "screening_run:READ", "*", "screening_run"):
            headers = {**dev_headers, DEV_PERMISSIONS_HEADER: permissions}
            response = await client.get(PROBE, headers=headers)
            assert response.status_code == 403, permissions

        # Principal with the permission -> 200.
        multi = {**dev_headers, DEV_PERMISSIONS_HEADER: "screening_run:create, screening_run:read"}
        response = await client.get(PROBE, headers=multi)
        assert response.status_code == 200
        assert response.json() == {"id": "user-1", "business_units": ["bu-1"]}

        # The public route needs no principal.
        assert (await client.get("/healthz")).status_code == 200


async def test_missing_provider_fails_closed() -> None:
    app = _app(AUTH_MODE="dev_header")
    del app.state.principal_provider
    async with _client(app) as client:
        response = await client.get(PROBE, headers={DEV_PRINCIPAL_ID_HEADER: "u"})
    assert response.status_code == 401
    assert isinstance(_app().state.principal_provider, DisabledPrincipalProvider)


def test_every_route_declares_permission() -> None:
    assert frozenset({"/healthz"}) == PUBLIC_ROUTES

    for overrides in ({}, {"AUTH_MODE": "dev_header", "FEATURE_SCREENING_RUNS": True}):
        settings = Settings(_env_file=None, DATABASE_URL=URL, **overrides)  # type: ignore[arg-type]
        app = create_app(settings)
        paths = {route.path for route in iter_route_contexts(app.routes)}
        assert paths == {"/healthz"}  # Phase 0 mounts no feature routes
        assert find_unprotected_routes(app) == [], overrides

    # The audit catches an unprotected route, a router-level permission counts as declared,
    # and non-API routes outside PUBLIC_ROUTES are reported.
    app = _app()
    assert PROBE in {route.path for route in iter_route_contexts(app.routes)}
    assert find_unprotected_routes(app) == []

    @app.get("/api/v1/unprotected")
    async def unprotected() -> dict[str, str]:
        return {}

    guarded = APIRouter(dependencies=[Depends(require_permission("screening_run:create"))])

    @guarded.post("/api/v1/guarded")
    async def guarded_route() -> dict[str, str]:
        return {}

    app.include_router(guarded)

    async def raw(_: object) -> None:
        return None

    app.router.routes.append(Route("/raw", raw))
    assert find_unprotected_routes(app) == ["GET /api/v1/unprotected", "Route /raw"]
    with pytest.raises(RuntimeError, match="without a required permission"):
        ensure_routes_protected(app)


def test_permission_names_are_validated() -> None:
    with pytest.raises(ValueError, match="<resource>:<action>"):
        require_permission("admin")


def test_create_app_refuses_unprotected_route(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-15: the factory itself refuses to start, not only the route-audit test."""
    import app.main as main

    leaky = APIRouter()

    @leaky.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @leaky.get("/api/v1/leak")
    async def leak() -> dict[str, str]:
        return {}

    monkeypatch.setattr(main, "health_router", leaky)
    settings = Settings(_env_file=None, DATABASE_URL=URL)  # type: ignore[call-arg]
    with pytest.raises(RuntimeError, match=r"GET /api/v1/leak"):
        create_app(settings)
