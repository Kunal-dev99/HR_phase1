"""Role brief schemas (D-35, D-36, D-37).

``RoleBriefOutputV1`` is the versioned contract for AI output: extra fields are forbidden
and every string is length-limited. Its ``model_json_schema()`` is what the provider is
asked to follow; the application validates the output regardless.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.role_briefs import constants as c
from app.modules.role_briefs.constants import Basis, RoleBriefStatus, Severity


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceRef(_Strict):
    path: str = Field(min_length=1, max_length=c.PATH_MAX, pattern=c.PATH_PATTERN)
    quote: str = Field(min_length=1, max_length=c.QUOTE_MAX)


class BriefItem(_Strict):
    text: str = Field(min_length=1, max_length=c.TEXT_MAX)
    basis: Basis
    source_refs: list[SourceRef] = Field(max_length=c.REFS_MAX)


class SourceFact(_Strict):
    statement: str = Field(min_length=1, max_length=c.TEXT_MAX)
    source_refs: list[SourceRef] = Field(max_length=c.REFS_MAX)


class AIInference(_Strict):
    statement: str = Field(min_length=1, max_length=c.TEXT_MAX)
    rationale: str = Field(min_length=1, max_length=c.TEXT_MAX)
    source_refs: list[SourceRef] = Field(max_length=c.REFS_MAX)


class Ambiguity(_Strict):
    topic: str = Field(min_length=1, max_length=c.SHORT_TEXT_MAX)
    description: str = Field(min_length=1, max_length=c.TEXT_MAX)
    severity: Severity
    suggested_question: str = Field(min_length=1, max_length=c.TEXT_MAX)


class RoleStructuredData(_Strict):
    """``role_brief_version.structured_role_data``."""

    role_title: BriefItem
    role_purpose: BriefItem
    responsibilities: list[BriefItem] = Field(max_length=c.LIST_MAX)
    required_capabilities: list[BriefItem] = Field(max_length=c.LIST_MAX)
    preferred_capabilities: list[BriefItem] = Field(max_length=c.LIST_MAX)
    seniority: BriefItem
    location_constraints: list[BriefItem] = Field(max_length=c.LIST_MAX)
    employment_constraints: list[BriefItem] = Field(max_length=c.LIST_MAX)


STRUCTURED_FIELDS: frozenset[str] = frozenset(RoleStructuredData.model_fields)


class RoleBriefOutputV1(RoleStructuredData):
    """AI output contract, schema version ``ROLE_BRIEF_SCHEMA_VERSION`` (= "1")."""

    explicit_source_facts: list[SourceFact] = Field(max_length=c.LIST_MAX)
    ai_inferences: list[AIInference] = Field(max_length=c.LIST_MAX)
    ambiguities: list[Ambiguity] = Field(max_length=c.LIST_MAX)


class RoleBriefCreate(_Strict):
    """Everything the repository needs to insert a version."""

    requisition_id: uuid.UUID
    screening_run_id: uuid.UUID
    version_number: int = Field(ge=1)
    status: RoleBriefStatus
    structured_role_data: RoleStructuredData
    explicit_source_facts: list[SourceFact]
    ai_inferences: list[AIInference]
    ambiguities: list[Ambiguity]
    source_snapshot_id: uuid.UUID
    source_payload_hash: str = Field(min_length=1, max_length=c.PAYLOAD_HASH_MAX)
    schema_version: str = Field(min_length=1, max_length=c.SCHEMA_VERSION_MAX)
    prompt_version: str = Field(min_length=1, max_length=c.PROMPT_VERSION_MAX)
    model_provider: str = Field(min_length=1, max_length=c.MODEL_PROVIDER_MAX)
    model_name: str = Field(min_length=1, max_length=c.MODEL_NAME_MAX)
    created_by: str = Field(min_length=1, max_length=c.CREATED_BY_MAX)


class RoleBriefResponse(BaseModel):
    """A brief version as the API returns it. Never carries the raw snapshot payload."""

    model_config = ConfigDict(from_attributes=True)

    role_brief_version_id: uuid.UUID
    screening_run_id: uuid.UUID
    requisition_id: uuid.UUID
    version_number: int
    status: RoleBriefStatus
    structured_role_data: RoleStructuredData
    explicit_source_facts: list[SourceFact]
    ai_inferences: list[AIInference]
    ambiguities: list[Ambiguity]
    schema_version: str
    prompt_version: str
    model_provider: str
    model_name: str
    source_snapshot_id: uuid.UUID
    source_payload_hash: str
    created_by: str
    created_at: datetime
    approved_by: str | None
    approved_at: datetime | None


class ApproveRoleBriefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_brief_version_id: uuid.UUID
