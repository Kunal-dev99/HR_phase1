"""Fixture-backed AI model adapter (BE-6.3, D-13, D-39). Development and tests only.

``AI_PROVIDER=mock`` is refused when ``ENVIRONMENT=production``. Fixtures are loaded once
from ``fixtures/role_brief_<routing_key>.json``; the routing key is only ever a dictionary
key, never part of a path.
"""

from __future__ import annotations

from pathlib import Path

from app.modules.integrations.adapters.ai_model.base import AIRequest, AIResponse, AIUnavailable
from app.modules.integrations.constants import MOCK_AI_MODEL, MOCK_AI_PROVIDER_KEY, AIErrorCode

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
FIXTURE_PREFIX = "role_brief_"

# Routing keys that simulate a provider outage instead of reading a fixture.
SIMULATED_UNAVAILABLE_KEYS: frozenset[str] = frozenset({"REQ-AI-UNAVAILABLE-1"})


def _load_fixtures(directory: Path) -> dict[str, str]:
    return {
        path.stem.removeprefix(FIXTURE_PREFIX): path.read_text(encoding="utf-8")
        for path in sorted(directory.glob(f"{FIXTURE_PREFIX}*.json"))
    }


class MockAIModelAdapter:
    def __init__(self, *, fixtures_dir: Path = FIXTURES_DIR) -> None:
        self._fixtures = _load_fixtures(fixtures_dir)

    @property
    def provider_key(self) -> str:
        return MOCK_AI_PROVIDER_KEY

    async def complete_json(self, request: AIRequest) -> AIResponse:
        if request.routing_key in SIMULATED_UNAVAILABLE_KEYS:
            raise AIUnavailable(AIErrorCode.UNAVAILABLE)
        content = self._fixtures.get(request.routing_key)
        if content is None:
            raise AIUnavailable(AIErrorCode.UNAVAILABLE)
        return AIResponse(content=content, model=MOCK_AI_MODEL, http_status=200)
