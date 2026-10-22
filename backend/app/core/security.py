"""Authentication and authorization primitives (BE-0.7, D-04, D-08).

* ``PUBLIC_ROUTES`` is the explicit allowlist of routes that need no principal.
* Every other route must depend on ``require_permission(name)``. ``find_unprotected_routes``
  enumerates the app's routes; ``create_app`` refuses to start if any route is unprotected.
* No principal -> 401. A principal without the permission -> 403.
* The principal comes from a pluggable ``PrincipalProvider``. The default
  (``AUTH_MODE=disabled``) never yields a principal, so every non-public route returns 401.
  ``DevHeaderPrincipalProvider`` is development-only and refused in production by settings.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Annotated, Protocol

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, RouteContext, iter_route_contexts
from starlette.routing import BaseRoute

from app.core.settings import AuthMode, Environment, Settings, UnsafeConfigurationError

PUBLIC_ROUTES: frozenset[str] = frozenset({"/healthz"})

PERMISSION_PATTERN = re.compile(r"[a-z][a-z0-9_]*:[a-z][a-z0-9_]*")
PRINCIPAL_ID_PATTERN = re.compile(r"[A-Za-z0-9._@-]{1,128}")
BUSINESS_UNIT_PATTERN = re.compile(r"\*|[A-Za-z0-9._-]{1,64}")

DEV_PRINCIPAL_ID_HEADER = "X-Dev-Principal-Id"
DEV_PERMISSIONS_HEADER = "X-Dev-Permissions"
DEV_BUSINESS_UNITS_HEADER = "X-Dev-Business-Units"

# Marker attribute set on every dependency returned by ``require_permission``.
PERMISSION_MARKER = "__required_permission__"


@dataclass(frozen=True, slots=True)
class Principal:
    id: str
    permissions: frozenset[str]
    business_units: frozenset[str]

    def has_permission(self, name: str) -> bool:
        return name in self.permissions


class PrincipalProvider(Protocol):
    async def get_principal(self, request: Request) -> Principal | None:
        """Return the authenticated principal, or ``None`` if there is none."""
        ...


class DisabledPrincipalProvider:
    """Default provider: authentication is disabled, so there is never a principal."""

    async def get_principal(self, request: Request) -> Principal | None:
        return None


def _split_header(value: str | None, pattern: re.Pattern[str]) -> frozenset[str]:
    if not value:
        return frozenset()
    items = (part.strip() for part in value.split(","))
    # Entries that do not match are dropped rather than trusted (fail closed).
    return frozenset(item for item in items if item and pattern.fullmatch(item))


class DevHeaderPrincipalProvider:
    """Development-only provider that trusts ``X-Dev-*`` headers (``AUTH_MODE=dev_header``)."""

    async def get_principal(self, request: Request) -> Principal | None:
        principal_id = (request.headers.get(DEV_PRINCIPAL_ID_HEADER) or "").strip()
        if not PRINCIPAL_ID_PATTERN.fullmatch(principal_id):
            return None
        return Principal(
            id=principal_id,
            permissions=_split_header(
                request.headers.get(DEV_PERMISSIONS_HEADER), PERMISSION_PATTERN
            ),
            business_units=_split_header(
                request.headers.get(DEV_BUSINESS_UNITS_HEADER), BUSINESS_UNIT_PATTERN
            ),
        )


def build_principal_provider(settings: Settings) -> PrincipalProvider:
    if settings.AUTH_MODE is AuthMode.DEV_HEADER:
        if settings.ENVIRONMENT is Environment.PRODUCTION:
            raise UnsafeConfigurationError(
                "AUTH_MODE=dev_header is not allowed when ENVIRONMENT=production"
            )
        return DevHeaderPrincipalProvider()
    return DisabledPrincipalProvider()


async def get_current_principal(request: Request) -> Principal:
    """Resolve the principal or reject with 401. A missing provider means disabled."""
    provider: PrincipalProvider = (
        getattr(request.app.state, "principal_provider", None) or DisabledPrincipalProvider()
    )
    principal = await provider.get_principal(request)
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return principal


def require_permission(name: str) -> Callable[[Principal], Awaitable[Principal]]:
    """Dependency factory: the route needs a principal holding permission ``name``."""
    if not PERMISSION_PATTERN.fullmatch(name):
        raise ValueError(f"permission names must be '<resource>:<action>', got {name!r}")

    async def _require(
        principal: Annotated[Principal, Depends(get_current_principal)],
    ) -> Principal:
        if not principal.has_permission(name):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return principal

    setattr(_require, PERMISSION_MARKER, name)
    _require.__name__ = f"require_permission[{name}]"
    return _require


def _declared_permissions(dependant: Dependant) -> set[str]:
    found: set[str] = set()
    stack = [dependant]
    while stack:
        current = stack.pop()
        marker = getattr(current.call, PERMISSION_MARKER, None)
        if isinstance(marker, str):
            found.add(marker)
        stack.extend(current.dependencies)
    return found


def route_permissions(route: RouteContext) -> set[str]:
    """Permissions declared on the effective route (router-level dependencies included)."""
    dependant = getattr(route, "dependant", None)
    return _declared_permissions(dependant) if isinstance(dependant, Dependant) else set()


def find_unprotected_routes(routes: Iterable[BaseRoute] | FastAPI) -> list[str]:
    """Every route outside ``PUBLIC_ROUTES`` without a ``require_permission`` dependency.

    ``iter_route_contexts`` flattens included routers, so paths carry their prefixes and
    dependencies declared on a router count for each of its routes.
    """
    items = list(routes.routes if isinstance(routes, FastAPI) else routes)
    unprotected: list[str] = []
    for route in iter_route_contexts(items):
        path = route.path or repr(route.original_route)
        if path in PUBLIC_ROUTES:
            continue
        if isinstance(route.original_route, APIRoute):
            if not route_permissions(route):
                methods = ",".join(sorted(route.methods or ()))
                unprotected.append(f"{methods} {path}")
        else:
            # Mounts, plain Starlette routes and websockets cannot carry the dependency:
            # anything that is not explicitly public is reported (fail closed).
            unprotected.append(f"{type(route.original_route).__name__} {path}")
    return unprotected


def ensure_routes_protected(app: FastAPI) -> None:
    unprotected = find_unprotected_routes(app)
    if unprotected:
        raise RuntimeError(f"routes without a required permission: {unprotected}")
