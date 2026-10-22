"""Fixture-backed HR System adapter (BE-1.4, D-13). Development and tests only.

``HR_SYSTEM_ADAPTER=mock`` is refused when ``ENVIRONMENT=production`` (settings, BE-0.2).

Fixtures are loaded once from ``fixtures/*.json`` and indexed by file stem. A requested ID
is only ever used as a dictionary key, never to build a path, so it cannot reach files
outside the fixture directory. Fixture content is parsed and validated as data.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import ValidationError

from app.modules.integrations.adapters.hr_system.base import (
    HRSystemUnavailable,
    InvalidHRResponse,
    RequisitionNotFound,
)
from app.modules.integrations.constants import MOCK_HR_SYSTEM_KEY
from app.modules.integrations.schemas import HRRequisitionPayload

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# IDs that simulate an HR System outage instead of reading a fixture.
SIMULATED_UNAVAILABLE_IDS: frozenset[str] = frozenset({"REQ-UNAVAILABLE"})


def _load_fixtures(directory: Path) -> dict[str, bytes]:
    return {path.stem: path.read_bytes() for path in sorted(directory.glob("*.json"))}


class MockHRSystemAdapter:
    def __init__(
        self, *, fixtures_dir: Path = FIXTURES_DIR, latency_seconds: float = 0.0
    ) -> None:
        self._fixtures = _load_fixtures(fixtures_dir)
        self._latency_seconds = latency_seconds

    @property
    def hr_system_key(self) -> str:
        return MOCK_HR_SYSTEM_KEY

    @property
    def fixture_ids(self) -> frozenset[str]:
        return frozenset(self._fixtures)

    async def get_requisition(self, external_requisition_id: str) -> HRRequisitionPayload:
        if self._latency_seconds > 0:
            await asyncio.sleep(self._latency_seconds)
        if external_requisition_id in SIMULATED_UNAVAILABLE_IDS:
            raise HRSystemUnavailable("HR System is unavailable (simulated)")
        raw = self._fixtures.get(external_requisition_id)
        if raw is None:
            raise RequisitionNotFound("requisition not found")
        try:
            return HRRequisitionPayload.model_validate_json(raw)
        except ValidationError as exc:
            # Field locations only: pydantic messages can echo input values.
            locations = sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()})
            raise InvalidHRResponse(
                f"HR response failed schema validation at: {', '.join(locations)}"
            ) from None
