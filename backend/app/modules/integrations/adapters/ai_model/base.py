"""AI model adapter contract and typed errors (BE-6.3, D-31, D-35, D-39).

The gateway is provider neutral: a request carries a fixed system prompt, the untrusted
user content, the JSON schema the output must follow and the model name. Error messages
never carry prompt or response content, headers or keys.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.modules.integrations.constants import AIErrorCode


@dataclass(frozen=True, slots=True)
class AIRequest:
    system_prompt: str
    user_content: str
    json_schema: dict[str, Any]
    model: str
    max_output_tokens: int
    # Non-sensitive metadata used only by the mock adapter; never sent to a provider.
    routing_key: str = field(default="", repr=False)


@dataclass(frozen=True, slots=True)
class AIResponse:
    content: str = field(repr=False)
    model: str
    http_status: int | None = None


class AIModelError(Exception):
    """Base class for expected AI provider failures."""

    def __init__(
        self, error_code: AIErrorCode | str, *, http_status: int | None = None
    ) -> None:
        self.error_code = AIErrorCode(error_code)
        self.http_status = http_status
        super().__init__(f"AI model call failed: {self.error_code.value}")


class AIUnavailable(AIModelError):  # noqa: N818 - name fixed by the plan (BE-6.3)
    """``timeout`` | ``unavailable`` | ``auth_failed`` | ``rate_limited``."""


class AIOutputInvalid(AIModelError):  # noqa: N818 - name fixed by the plan (BE-6.3)
    """``invalid_json`` | ``schema_invalid`` | ``refused`` | ``citation_unverified`` |
    ``uncited_requirement``."""


class AIModelAdapter(Protocol):
    @property
    def provider_key(self) -> str:
        """Provider name recorded on every brief (``model_provider``)."""
        ...

    async def complete_json(self, request: AIRequest) -> AIResponse:
        """One call, no retries (D-06). Raises ``AIUnavailable`` or ``AIOutputInvalid``."""
        ...
