"""Audit HTTP routes: none (ARCHITECTURE.md: audit is append-only, no endpoints).

The router exists to keep the standard module shape. It is not mounted, and any route
added here later must declare ``require_permission`` (D-04).
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/audit", tags=["audit"])
