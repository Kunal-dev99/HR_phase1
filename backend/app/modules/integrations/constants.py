"""Integrations constants (Data Model §4.17, D-06, D-13)."""

from __future__ import annotations

from enum import StrEnum

INTEGRATION_ATTEMPT_TABLE = "integration_attempt"

INTEGRATION_HR_SYSTEM = "hr_system"
OPERATION_GET_REQUISITION = "get_requisition"

# Selected by settings.HR_SYSTEM_ADAPTER; also the ``hr_system_key`` the mock reports.
MOCK_HR_SYSTEM_KEY = "mock"

# D-06: a single attempt per call, no retries yet.
FIRST_ATTEMPT = 1


class AttemptOutcome(StrEnum):
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    INVALID_RESPONSE = "invalid_response"


class HRErrorCode(StrEnum):
    """``integration_attempt.error_code`` values for the HR System."""

    NOT_FOUND = "requisition_not_found"
    UNAVAILABLE = "hr_system_unavailable"
    TIMEOUT = "hr_system_timeout"
    ADAPTER_ERROR = "hr_adapter_error"
    INVALID_RESPONSE = "hr_response_invalid"
    ID_MISMATCH = "hr_response_id_mismatch"


# Column limits.
INTEGRATION_NAME_MAX = 64
OPERATION_MAX = 64
CORRELATION_ID_MAX = 64
IDEMPOTENCY_KEY_MAX = 128
REFERENCE_MAX = 512
OUTCOME_MAX = 32
ERROR_CODE_MAX = 64

# HR payload limits (mock vocabulary until the real contract is mapped, Data Model §2.10).
HR_TEXT_MAX = 20_000
HR_SHORT_TEXT_MAX = 512
HR_LIST_MAX = 100
