"""Integrations service: adapter selection and recorded HR System and AI calls (BE-1.4, BE-6.3).

``HRSystemService.fetch_requisition`` is the only way other modules' services reach the HR
System. Each call:

* runs under a per-call timeout (``HR_SYSTEM_TIMEOUT_SECONDS``);
* is a single attempt (D-06);
* checks that the response is for the requested requisition;
* writes one ``integration_attempt`` row (operation, correlation_id, attempt_number=1,
  outcome, error_code) and never stores or logs the payload.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import Environment, Settings, UnsafeConfigurationError
from app.modules.integrations import constants as c
from app.modules.integrations.adapters.ai_model.base import (
    AIModelAdapter,
    AIModelError,
    AIOutputInvalid,
    AIRequest,
    AIUnavailable,
)
from app.modules.integrations.adapters.ai_model.groq import GroqAdapter
from app.modules.integrations.adapters.ai_model.mock import MockAIModelAdapter
from app.modules.integrations.adapters.hr_system.base import (
    HRSystemAdapter,
    HRSystemError,
    HRSystemUnavailable,
    InvalidHRResponse,
)
from app.modules.integrations.adapters.hr_system.mock import MockHRSystemAdapter
from app.modules.integrations.constants import AIErrorCode, AttemptOutcome, HRErrorCode
from app.modules.integrations.repository import IntegrationAttemptRepository
from app.modules.integrations.schemas import (
    HRRequisitionPayload,
    IntegrationAttemptCreate,
    IntegrationAttemptRead,
)

logger = logging.getLogger("app.integrations")


class HRSystemNotConfiguredError(RuntimeError):
    """``HR_SYSTEM_ADAPTER`` is unset or names an unknown adapter."""


def build_hr_system_adapter(settings: Settings) -> HRSystemAdapter:
    """Select the adapter named by ``HR_SYSTEM_ADAPTER``. Unset or unknown fails closed."""
    name = (settings.HR_SYSTEM_ADAPTER or "").strip().lower()
    if not name:
        raise HRSystemNotConfiguredError("HR_SYSTEM_ADAPTER is not set")
    if name == c.MOCK_HR_SYSTEM_KEY:
        if settings.ENVIRONMENT is Environment.PRODUCTION:
            raise UnsafeConfigurationError(
                "HR_SYSTEM_ADAPTER=mock is not allowed when ENVIRONMENT=production"
            )
        return MockHRSystemAdapter()
    raise HRSystemNotConfiguredError(f"unknown HR_SYSTEM_ADAPTER {name!r}")


@dataclass(frozen=True, slots=True)
class HRFetchResult:
    """Exactly one of ``payload`` and ``error`` is set."""

    attempt: IntegrationAttemptRead
    payload: HRRequisitionPayload | None = None
    error: HRSystemError | None = None


class HRSystemService:
    def __init__(
        self,
        adapter: HRSystemAdapter,
        attempts: IntegrationAttemptRepository,
        *,
        timeout_seconds: float,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._adapter = adapter
        self._attempts = attempts
        self._timeout_seconds = timeout_seconds

    @classmethod
    def for_session(
        cls, session: AsyncSession, adapter: HRSystemAdapter, *, timeout_seconds: float
    ) -> HRSystemService:
        return cls(adapter, IntegrationAttemptRepository(session), timeout_seconds=timeout_seconds)

    @property
    def hr_system_key(self) -> str:
        return self._adapter.hr_system_key

    async def _call(self, external_requisition_id: str) -> HRRequisitionPayload:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                payload = await self._adapter.get_requisition(external_requisition_id)
        except TimeoutError:
            raise HRSystemUnavailable(
                "HR System call timed out", error_code=HRErrorCode.TIMEOUT
            ) from None
        except HRSystemError:
            raise
        except Exception as exc:
            # An unexpected adapter failure blocks the run rather than leaving it stuck.
            logger.warning(
                "HR System adapter raised an unexpected error",
                extra={"event": "hr_adapter_error"},
                exc_info=exc,
            )
            raise HRSystemUnavailable(
                "HR System adapter failed", error_code=HRErrorCode.ADAPTER_ERROR
            ) from None
        if not isinstance(payload, HRRequisitionPayload):
            raise InvalidHRResponse("adapter returned an unvalidated payload")
        if payload.external_requisition_id != external_requisition_id:
            raise InvalidHRResponse(
                "HR response is for a different requisition", error_code=HRErrorCode.ID_MISMATCH
            )
        return payload

    async def fetch_requisition(
        self,
        *,
        screening_run_id: uuid.UUID,
        external_requisition_id: str,
        correlation_id: str,
    ) -> HRFetchResult:
        """Call the adapter once and record the attempt in the caller's transaction."""
        started_at = datetime.now(UTC)
        payload: HRRequisitionPayload | None = None
        error: HRSystemError | None = None
        try:
            payload = await self._call(external_requisition_id)
        except HRSystemError as exc:
            error = exc
        attempt = await self._attempts.add(
            IntegrationAttemptCreate(
                screening_run_id=screening_run_id,
                integration_name=c.INTEGRATION_HR_SYSTEM,
                operation=c.OPERATION_GET_REQUISITION,
                correlation_id=correlation_id,
                attempt_number=c.FIRST_ATTEMPT,
                outcome=AttemptOutcome.SUCCESS if error is None else error.outcome,
                error_code=None if error is None else error.error_code.value,
                started_at=started_at,
                completed_at=datetime.now(UTC),
            )
        )
        return HRFetchResult(
            attempt=IntegrationAttemptRead.model_validate(attempt), payload=payload, error=error
        )

    async def list_attempts(self, screening_run_id: uuid.UUID) -> list[IntegrationAttemptRead]:
        rows = await self._attempts.list_for_run(screening_run_id)
        return [IntegrationAttemptRead.model_validate(r) for r in rows]


# --- AI model gateway (BE-6.3, D-31, D-35, D-39) ------------------------------------------


class AIModelNotConfiguredError(RuntimeError):
    """``AI_PROVIDER`` is unset or names an unknown provider."""


def build_ai_model_adapter(settings: Settings) -> AIModelAdapter:
    """Select the adapter named by ``AI_PROVIDER``. Unset or unknown fails closed."""
    name = (settings.AI_PROVIDER or "").strip().lower()
    if not name:
        raise AIModelNotConfiguredError("AI_PROVIDER is not set")
    if name == c.MOCK_AI_PROVIDER_KEY:
        if settings.ENVIRONMENT is Environment.PRODUCTION:
            raise UnsafeConfigurationError(
                "AI_PROVIDER=mock is not allowed when ENVIRONMENT=production"
            )
        return MockAIModelAdapter()
    if name == c.GROQ_AI_PROVIDER_KEY:
        key = settings.GROQ_API_KEY
        if key is None or not key.get_secret_value().strip():
            raise AIModelNotConfiguredError("AI_PROVIDER=groq requires GROQ_API_KEY")
        return GroqAdapter(
            api_key=key,
            base_url=settings.GROQ_BASE_URL,
            timeout_seconds=settings.AI_TIMEOUT_SECONDS,
        )
    raise AIModelNotConfiguredError(f"unknown AI_PROVIDER {name!r}")


@dataclass(frozen=True, slots=True)
class AIStructuredResult[M: BaseModel]:
    output: M
    provider: str
    model: str


_AI_OUTCOMES: dict[AIErrorCode, AttemptOutcome] = {
    AIErrorCode.TIMEOUT: AttemptOutcome.TIMEOUT,
    AIErrorCode.UNAVAILABLE: AttemptOutcome.UNAVAILABLE,
    AIErrorCode.AUTH_FAILED: AttemptOutcome.UNAVAILABLE,
    AIErrorCode.RATE_LIMITED: AttemptOutcome.UNAVAILABLE,
}


def _validation_locations(exc: ValidationError) -> str:
    # Field locations only: pydantic messages can echo model output.
    return ", ".join(sorted({".".join(str(p) for p in e["loc"]) or "<root>" for e in exc.errors()}))


class AIGatewayService:
    """The only way other modules' services reach an AI model.

    Each call runs under ``AI_TIMEOUT_SECONDS``, is a single attempt (D-06), parses and
    schema-validates the output, and writes one ``integration_attempt`` (no bodies) in the
    caller's unit of work. The DB is touched only after the provider call returns, so no
    transaction is held open across it (D-32).
    """

    def __init__(
        self,
        adapter: AIModelAdapter,
        attempts: IntegrationAttemptRepository,
        *,
        timeout_seconds: float,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._adapter = adapter
        self._attempts = attempts
        self._timeout_seconds = timeout_seconds

    @classmethod
    def for_session(
        cls, session: AsyncSession, adapter: AIModelAdapter, *, timeout_seconds: float
    ) -> AIGatewayService:
        return cls(adapter, IntegrationAttemptRepository(session), timeout_seconds=timeout_seconds)

    @property
    def provider_key(self) -> str:
        return self._adapter.provider_key

    async def _call[M: BaseModel](
        self, request: AIRequest, output_model: type[M]
    ) -> tuple[M, str, int | None]:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                response = await self._adapter.complete_json(request)
        except TimeoutError:
            raise AIUnavailable(AIErrorCode.TIMEOUT) from None
        except AIModelError:
            raise
        except Exception as exc:
            logger.warning(
                "AI adapter raised an unexpected error",
                extra={"event": "ai_adapter_error", "error_type": type(exc).__name__},
            )
            raise AIUnavailable(AIErrorCode.UNAVAILABLE) from None
        try:
            data = json.loads(response.content)
        except ValueError:
            raise AIOutputInvalid(
                AIErrorCode.INVALID_JSON, http_status=response.http_status
            ) from None
        try:
            output = output_model.model_validate(data)
        except ValidationError as exc:
            logger.info(
                "AI output failed schema validation",
                extra={"event": "ai_output_invalid", "locations": _validation_locations(exc)},
            )
            raise AIOutputInvalid(
                AIErrorCode.SCHEMA_INVALID, http_status=response.http_status
            ) from None
        return output, response.model, response.http_status

    async def generate_structured[M: BaseModel](
        self,
        request: AIRequest,
        output_model: type[M],
        *,
        screening_run_id: uuid.UUID,
        correlation_id: str,
        operation: str = c.OPERATION_ROLE_BRIEF_GENERATE,
    ) -> AIStructuredResult[M]:
        """Call the model once; raise ``AIUnavailable``/``AIOutputInvalid`` after recording."""
        started_at = datetime.now(UTC)
        error: AIModelError | None = None
        result: tuple[M, str, int | None] | None = None
        try:
            result = await self._call(request, output_model)
        except AIModelError as exc:
            error = exc
        if error is None:
            outcome = AttemptOutcome.SUCCESS
            http_status = result[2] if result else None
        elif isinstance(error, AIUnavailable):
            outcome = _AI_OUTCOMES.get(error.error_code, AttemptOutcome.UNAVAILABLE)
            http_status = error.http_status
        else:
            outcome = AttemptOutcome.INVALID_RESPONSE
            http_status = error.http_status
        await self._attempts.add(
            IntegrationAttemptCreate(
                screening_run_id=screening_run_id,
                integration_name=c.INTEGRATION_AI_MODEL,
                operation=operation,
                correlation_id=correlation_id,
                attempt_number=c.FIRST_ATTEMPT,
                outcome=outcome,
                error_code=None if error is None else error.error_code.value,
                http_status=http_status,
                started_at=started_at,
                completed_at=datetime.now(UTC),
            )
        )
        if error is not None:
            raise error
        if result is None:  # invariant: either an error or a result
            raise RuntimeError("AI call produced neither a result nor an error")
        output, model, _ = result
        return AIStructuredResult(output=output, provider=self._adapter.provider_key, model=model)
