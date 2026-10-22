"""Integrations HTTP routes: none in Phase 1 (no HTTP; DELIVERY_PLAN Phase 1 goal).

The router keeps the standard module shape and is not mounted. Any route added later must
declare ``require_permission`` (D-04) and call only this module's services.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["integrations"])
