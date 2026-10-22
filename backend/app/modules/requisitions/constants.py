"""Requisitions constants: run states, reason codes and versioned rules (D-07, D-09, D-10).

Statuses and reason codes are application enums stored as strings. There is deliberately
no database CHECK constraint, so later states stay additive (D-01, D-10).
"""

from __future__ import annotations

from enum import StrEnum

REQUISITION_TABLE = "requisition"
SNAPSHOT_TABLE = "requisition_snapshot"
SNAPSHOT_PAYLOAD_TABLE = "requisition_snapshot_payload"
SCREENING_RUN_TABLE = "screening_run"


class RunStatus(StrEnum):
    """Screening-run states (Data Model §7.1). This feature drives the first three + blocked."""

    CREATED = "created"
    INGESTING_REQUISITION = "ingesting_requisition"
    ROLE_BRIEF_DRAFT = "role_brief_draft"
    AWAITING_ROLE_APPROVAL = "awaiting_role_approval"
    ROLE_CONFIGURATION = "role_configuration"
    AWAITING_CONFIGURATION_APPROVAL = "awaiting_configuration_approval"
    SOURCING = "sourcing"
    CANDIDATE_POOL_READY = "candidate_pool_ready"
    EVALUATING_PROFILES = "evaluating_profiles"
    ASSESSMENT_PROCESSING = "assessment_processing"
    SHORTLIST_READY = "shortlist_ready"
    WRITING_BACK_TO_HR = "writing_back_to_hr"
    COMPLETED = "completed"
    COMPLETED_WITH_EXCEPTIONS = "completed_with_exceptions"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class CompletionReason(StrEnum):
    """Public ``completion_reason`` codes for a blocked run (D-07)."""

    REQUISITION_NOT_FOUND = "requisition_not_found"
    REQUISITION_NOT_ELIGIBLE_STATUS = "requisition_not_eligible_status"
    REQUISITION_INCOMPLETE = "requisition_incomplete"
    HR_SYSTEM_UNAVAILABLE = "hr_system_unavailable"
    HR_RESPONSE_INVALID = "hr_response_invalid"
    INGESTION_INTERRUPTED = "ingestion_interrupted"


class AuditReason(StrEnum):
    """Audit-only ``reason_code`` values, never exposed as a ``completion_reason``."""

    INGESTION_CLAIMED = "ingestion_claimed"
    REQUISITION_ELIGIBLE = "requisition_eligible"
    # D-09: the run shows requisition_not_found; only the audit records the true reason.
    REQUISITION_NOT_ACCESSIBLE = "requisition_not_accessible"


# Snapshot ingestion schema version (Data Model §4.2 ``schema_version``, D-05).
REQUISITION_INGESTION_SCHEMA_VERSION = "1"
PAYLOAD_REFERENCE_PREFIX = f"db:{SNAPSHOT_PAYLOAD_TABLE}:"
PAYLOAD_HASH_PREFIX = "sha256:"

# Eligibility rules, version 1 (D-07). Changing a rule means bumping the version.
ELIGIBILITY_RULES_VERSION = "1"
ELIGIBILITY_REQUIRED_FIELDS: tuple[str, ...] = ("title", "description")
DEFAULT_ELIGIBLE_SOURCE_STATUSES: tuple[str, ...] = ("open",)

# Audit actor conventions (D-12).
INGESTION_ACTOR_ID = "requisitions.ingestion"
ENTITY_SCREENING_RUN = "screening_run"
ENTITY_REQUISITION = "requisition"
ENTITY_REQUISITION_SNAPSHOT = "requisition_snapshot"

# Permissions (D-08). Checked again in the service as defence in depth.
PERMISSION_SCREENING_RUN_CREATE = "screening_run:create"
PERMISSION_SCREENING_RUN_READ = "screening_run:read"

# Row scoping (D-09): honoured only when explicitly granted to the principal.
WILDCARD_BUSINESS_UNIT = "*"

# Column limits, shared by the models, the migration and the schemas.
HR_SYSTEM_KEY_MAX = 64
EXTERNAL_REQUISITION_ID_MAX = 128
EXTERNAL_VERSION_MAX = 128
SOURCE_STATUS_MAX = 64
BUSINESS_UNIT_KEY_MAX = 64
PAYLOAD_REFERENCE_MAX = 512
PAYLOAD_HASH_MAX = 80
SCHEMA_VERSION_MAX = 16
STATUS_MAX = 64
STARTED_BY_MAX = 128
CORRELATION_ID_MAX = 64
COMPLETION_REASON_MAX = 64

# Screening-run API (D-11). phases.phase_1 is derived from the run status.
SCREENING_RUNS_PATH = "/screening-runs"
PHASE_PENDING = "pending"
PHASE_IN_PROGRESS = "in_progress"
PHASE_BLOCKED = "blocked"
PHASE_1_BY_STATUS: dict[RunStatus, str] = {
    RunStatus.CREATED: PHASE_PENDING,
    RunStatus.INGESTING_REQUISITION: PHASE_IN_PROGRESS,
    RunStatus.ROLE_BRIEF_DRAFT: PHASE_IN_PROGRESS,
    RunStatus.BLOCKED: PHASE_BLOCKED,
}
