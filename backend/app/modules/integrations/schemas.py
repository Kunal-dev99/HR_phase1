"""Integrations schemas.

``HRRequisitionPayload`` validates what an HR System adapter returns before anything else
uses it. HR content is data, never instructions. The field vocabulary is the mock's until
the real HR System contract is mapped (Data Model §2.10); fields the source does not send
stay unset (no defaults are invented).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.modules.integrations import constants as c
from app.modules.integrations.constants import AttemptOutcome

_BUSINESS_UNIT_PATTERN = r"^[A-Za-z0-9._-]{1,64}$"  # no wildcard: "*" is a principal grant only


class HRRequisitionPayload(BaseModel):
    """A requisition as returned by the HR System (validated, unknown fields ignored)."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    external_requisition_id: str = Field(min_length=1, max_length=128)
    status: str = Field(min_length=1, max_length=64, pattern=r"\S")
    business_unit: str = Field(pattern=_BUSINESS_UNIT_PATTERN)
    external_version: str | None = Field(default=None, max_length=128)
    last_modified_at: AwareDatetime | None = None
    # Content fields. Blank or missing title/description is an eligibility question (D-07),
    # not a validation error, so they are optional here.
    title: str | None = Field(default=None, max_length=c.HR_SHORT_TEXT_MAX)
    description: str | None = Field(default=None, max_length=c.HR_TEXT_MAX)
    responsibilities: list[str] | None = Field(default=None, max_length=c.HR_LIST_MAX)
    required_skills: list[str] | None = Field(default=None, max_length=c.HR_LIST_MAX)
    preferred_skills: list[str] | None = Field(default=None, max_length=c.HR_LIST_MAX)
    seniority: str | None = Field(default=None, max_length=c.HR_SHORT_TEXT_MAX)
    location: str | None = Field(default=None, max_length=c.HR_SHORT_TEXT_MAX)
    employment_type: str | None = Field(default=None, max_length=c.HR_SHORT_TEXT_MAX)
    department: str | None = Field(default=None, max_length=c.HR_SHORT_TEXT_MAX)

    def source_document(self) -> dict[str, object]:
        """Exactly the fields the source sent (validated), as JSON-compatible values."""
        return self.model_dump(mode="json", exclude_unset=True)


class IntegrationAttemptCreate(BaseModel):
    """An external call record. There is deliberately no body/payload field."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    screening_run_id: uuid.UUID
    integration_name: str = Field(min_length=1, max_length=c.INTEGRATION_NAME_MAX)
    operation: str = Field(min_length=1, max_length=c.OPERATION_MAX)
    correlation_id: str = Field(
        min_length=1, max_length=c.CORRELATION_ID_MAX, pattern=r"^[A-Za-z0-9-]+$"
    )
    attempt_number: int = Field(ge=1)
    outcome: AttemptOutcome
    error_code: str | None = Field(default=None, max_length=c.ERROR_CODE_MAX)
    http_status: int | None = None
    started_at: datetime
    completed_at: datetime | None = None


class IntegrationAttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    screening_run_id: uuid.UUID
    integration_name: str
    operation: str
    correlation_id: str
    idempotency_key: str | None
    attempt_number: int
    request_reference: str | None
    response_reference: str | None
    http_status: int | None
    outcome: AttemptOutcome
    error_code: str | None
    started_at: datetime
    completed_at: datetime | None
    next_retry_at: datetime | None
