"""Requisitions schemas. Read models never carry the raw snapshot payload (D-11)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.requisitions import constants as c
from app.modules.requisitions.constants import CompletionReason, RunStatus


class RequisitionUpsert(BaseModel):
    """Source fields copied from a validated HR payload. Nothing is defaulted or invented."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    hr_system_key: str = Field(min_length=1, max_length=c.HR_SYSTEM_KEY_MAX)
    external_requisition_id: str = Field(min_length=1, max_length=c.EXTERNAL_REQUISITION_ID_MAX)
    external_version: str | None = Field(default=None, max_length=c.EXTERNAL_VERSION_MAX)
    source_status: str = Field(min_length=1, max_length=c.SOURCE_STATUS_MAX)
    business_unit_key: str = Field(min_length=1, max_length=c.BUSINESS_UNIT_KEY_MAX)
    last_source_modified_at: datetime | None = None


class RequisitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    hr_system_key: str
    external_requisition_id: str
    external_version: str | None
    source_status: str
    business_unit_key: str
    last_source_modified_at: datetime | None
    last_synced_at: datetime
    created_at: datetime
    updated_at: datetime


class SnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    requisition_id: uuid.UUID
    external_version: str | None
    payload_reference: str
    payload_hash: str
    captured_at: datetime
    schema_version: str


class SnapshotCapture(BaseModel):
    """Result of ``SnapshotService.capture``: the pinned snapshot and whether it was reused."""

    model_config = ConfigDict(frozen=True)

    snapshot: SnapshotRead
    reused: bool


class ScreeningRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    requisition_id: uuid.UUID | None
    requisition_snapshot_id: uuid.UUID | None
    role_brief_version_id: uuid.UUID | None
    role_configuration_version_id: uuid.UUID | None
    hr_system_key: str
    external_requisition_id: str
    business_unit_key: str | None
    status: RunStatus
    status_details: dict[str, Any] | None
    started_by: str | None
    correlation_id: str
    started_at: datetime
    completed_at: datetime | None
    completion_reason: CompletionReason | None
    created_at: datetime


class EligibilityResult(BaseModel):
    """Outcome of ``check_eligibility`` (D-07). ``reason_code`` is None when eligible."""

    model_config = ConfigDict(frozen=True)

    eligible: bool
    reason_code: CompletionReason | None
    missing_fields: tuple[str, ...]
    rules_version: str


# --- Screening-run API (BE-2.3, BE-2.4, D-11) ---------------------------------------------


class ScreeningRunCreateRequest(BaseModel):
    """POST body: the HR System's requisition ID (not an internal UUID). Extra fields 422."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    external_requisition_id: str = Field(min_length=1, max_length=c.EXTERNAL_REQUISITION_ID_MAX)


class ScreeningRunAccepted(BaseModel):
    run_id: uuid.UUID
    status: RunStatus
    status_url: str
    correlation_id: str


class RunPhases(BaseModel):
    phase_1: str


class RunRequisitionReference(BaseModel):
    """A reference to the pinned snapshot. Never the raw payload (D-11)."""

    external_requisition_id: str
    hr_system_key: str
    requisition_id: uuid.UUID
    snapshot_id: uuid.UUID | None
    payload_hash: str | None
    captured_at: datetime | None


class ScreeningRunStatusResponse(BaseModel):
    run_id: uuid.UUID
    status: RunStatus
    phases: RunPhases
    completion_reason: CompletionReason | None
    status_details: dict[str, Any] | None
    requisition: RunRequisitionReference | None
    started_at: datetime
    completed_at: datetime | None
    correlation_id: str
