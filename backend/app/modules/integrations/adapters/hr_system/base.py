"""HR System adapter contract and typed errors (BE-1.4, Tech Arch §6.3).

Error messages never carry payload content: they name the requisition ID and, for invalid
responses, only the locations of the failing fields.
"""

from __future__ import annotations

from typing import Protocol

from app.modules.integrations.constants import AttemptOutcome, HRErrorCode
from app.modules.integrations.schemas import HRRequisitionPayload


class HRSystemError(Exception):
    """Base class for expected HR System failures."""

    outcome: AttemptOutcome = AttemptOutcome.UNAVAILABLE
    default_code: HRErrorCode = HRErrorCode.UNAVAILABLE

    def __init__(self, message: str, *, error_code: HRErrorCode | None = None) -> None:
        super().__init__(message)
        self.error_code: HRErrorCode = error_code or self.default_code


class RequisitionNotFound(HRSystemError):  # noqa: N818 - name fixed by the plan (BE-1.4)
    outcome = AttemptOutcome.NOT_FOUND
    default_code = HRErrorCode.NOT_FOUND


class HRSystemUnavailable(HRSystemError):  # noqa: N818 - name fixed by the plan (BE-1.4)
    outcome = AttemptOutcome.UNAVAILABLE
    default_code = HRErrorCode.UNAVAILABLE

    def __init__(self, message: str, *, error_code: HRErrorCode | None = None) -> None:
        super().__init__(message, error_code=error_code)
        if self.error_code is HRErrorCode.TIMEOUT:
            self.outcome = AttemptOutcome.TIMEOUT


class InvalidHRResponse(HRSystemError):  # noqa: N818 - name fixed by the plan (BE-1.4)
    outcome = AttemptOutcome.INVALID_RESPONSE
    default_code = HRErrorCode.INVALID_RESPONSE


class HRSystemAdapter(Protocol):
    """Contract every HR System adapter implements."""

    @property
    def hr_system_key(self) -> str:
        """Identifies the HR System instance/provider (``requisition.hr_system_key``)."""
        ...

    async def get_requisition(self, external_requisition_id: str) -> HRRequisitionPayload:
        """Return the validated requisition.

        Raises ``RequisitionNotFound``, ``HRSystemUnavailable`` or ``InvalidHRResponse``.
        """
        ...
