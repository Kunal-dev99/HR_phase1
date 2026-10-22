"""Groq adapter over its OpenAI-compatible HTTP API (BE-6.3, D-31, D-35, D-37, D-39).

One POST to ``{GROQ_BASE_URL}/chat/completions`` per call: no retries (D-06), no tools,
temperature 0 and a JSON-schema ``response_format``. The API key is read from the
``SecretStr`` only when the request is built. Nothing here logs, or puts into an exception,
the key, the headers, the prompt or the response body.
"""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import SecretStr

from app.modules.integrations.adapters.ai_model.base import (
    AIOutputInvalid,
    AIRequest,
    AIResponse,
    AIUnavailable,
)
from app.modules.integrations.constants import (
    AI_JSON_SCHEMA_NAME,
    GROQ_AI_PROVIDER_KEY,
    AIErrorCode,
)


def _status_error(status_code: int) -> AIUnavailable:
    if status_code in (401, 403):
        return AIUnavailable(AIErrorCode.AUTH_FAILED, http_status=status_code)
    if status_code == 429:
        return AIUnavailable(AIErrorCode.RATE_LIMITED, http_status=status_code)
    return AIUnavailable(AIErrorCode.UNAVAILABLE, http_status=status_code)


class GroqAdapter:
    def __init__(
        self,
        *,
        api_key: SecretStr,
        base_url: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    @property
    def provider_key(self) -> str:
        return GROQ_AI_PROVIDER_KEY

    def _body(self, request: AIRequest) -> dict[str, Any]:
        return {
            "model": request.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_content},
            ],
            "temperature": 0,
            "max_completion_tokens": request.max_output_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": AI_JSON_SCHEMA_NAME, "schema": request.json_schema},
            },
        }

    async def complete_json(self, request: AIRequest) -> AIResponse:
        headers = {"Authorization": f"Bearer {self._api_key.get_secret_value()}"}
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds, transport=self._transport
            ) as client:
                response = await client.post(self._url, json=self._body(request), headers=headers)
        except httpx.TimeoutException:
            raise AIUnavailable(AIErrorCode.TIMEOUT) from None
        except httpx.HTTPError:
            raise AIUnavailable(AIErrorCode.UNAVAILABLE) from None
        if response.status_code == 400:
            # Groq answers 400 when the model's output fails its own JSON-schema check.
            raise AIOutputInvalid(AIErrorCode.INVALID_JSON, http_status=400)
        if response.status_code != 200:
            raise _status_error(response.status_code)
        try:
            data = response.json()
            choice = data["choices"][0]
            message = choice["message"]
            model = str(data.get("model") or request.model)
        except (ValueError, KeyError, IndexError, TypeError):
            raise AIOutputInvalid(AIErrorCode.INVALID_JSON, http_status=200) from None
        if message.get("refusal"):
            raise AIOutputInvalid(AIErrorCode.REFUSED, http_status=200)
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise AIOutputInvalid(AIErrorCode.INVALID_JSON, http_status=200)
        return AIResponse(content=content, model=model, http_status=200)

