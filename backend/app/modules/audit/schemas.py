"""Audit schemas. ``details`` holds small non-PII facts only (D-12)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.audit import constants as c
from app.modules.audit.constants import ActorType

DetailValue = str | int | float | bool | None | list[str]

_CODE_PATTERN = r"^[A-Za-z][A-Za-z0-9_.:-]*$"


class AuditEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    screening_run_id: uuid.UUID
    entity_type: str = Field(min_length=1, max_length=c.ENTITY_TYPE_MAX, pattern=_CODE_PATTERN)
    entity_id: str = Field(min_length=1, max_length=c.ENTITY_ID_MAX)
    event_type: str = Field(min_length=1, max_length=c.EVENT_TYPE_MAX, pattern=_CODE_PATTERN)
    actor_type: ActorType
    actor_id: str | None = Field(default=None, min_length=1, max_length=c.ACTOR_ID_MAX)
    correlation_id: str = Field(
        min_length=1, max_length=c.CORRELATION_ID_MAX, pattern=r"^[A-Za-z0-9-]+$"
    )
    configuration_version_id: uuid.UUID | None = None
    reason_code: str | None = Field(
        default=None, min_length=1, max_length=c.REASON_CODE_MAX, pattern=_CODE_PATTERN
    )
    details_reference: str | None = Field(
        default=None, min_length=1, max_length=c.DETAILS_REFERENCE_MAX
    )
    details: dict[str, DetailValue] | None = None

    @field_validator("details")
    @classmethod
    def _small_details(cls, value: dict[str, DetailValue] | None) -> dict[str, DetailValue] | None:
        if value is None:
            return None
        if len(value) > c.DETAILS_MAX_KEYS:
            raise ValueError(f"details may hold at most {c.DETAILS_MAX_KEYS} keys")
        for key, item in value.items():
            strings = item if isinstance(item, list) else [item]
            for s in [key, *strings]:
                if isinstance(s, str) and len(s) > c.DETAILS_MAX_STRING:
                    raise ValueError("details strings must be short, non-PII facts")
        return value


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    screening_run_id: uuid.UUID
    entity_type: str
    entity_id: str
    event_type: str
    actor_type: ActorType
    actor_id: str | None
    timestamp: datetime
    correlation_id: str
    configuration_version_id: uuid.UUID | None
    reason_code: str | None
    details_reference: str | None
    details: dict[str, DetailValue] | None
