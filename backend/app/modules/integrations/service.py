"""Integrations service: adapter selection and recorded HR System calls (BE-1.4).

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
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import Environment, Settings, UnsafeConfigurationError
from app.modules.integrations import constants as c
from app.modules.integrations.adapters.hr_system.base import (
    HRSystemAdapter,
    HRSystemError,
    HRSystemUnavailable,
    InvalidHRResponse,
)
from app.modules.integrations.adapters.hr_system.mock import MockHRSystemAdapter
from app.modules.integrations.constants import AttemptOutcome, HRErrorCode
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
