# AI-Enabled Recruitment Screening System

## Data Model Document: Phases 1--4

**Status:** Proposed logical data model for technical review\
**Scope:** HR System requisition ingestion through shortlist write-back\
**External systems:** HR System and Fusion Mind (Level 1 assessment
only)\
**Important:** This is a proposed logical model. Exact columns,
constraints, provider IDs, API payloads, retention rules, and status
mappings must be finalized after reviewing the HR System and Fusion Mind
contracts.

------------------------------------------------------------------------

## 1. Purpose

This document defines the proposed data model for the AI-enabled
recruitment screening system. It identifies the principal entities,
their relationships, key attributes, lifecycle states, data ownership,
and integrity rules across:

1.  Job Requirement Understanding.
2.  Role & Assessment Intelligence.
3.  Candidate Sourcing:
    -   3A Applicant-led Recruitment from the HR System.
    -   3B Proactive Talent Discovery through approved sources.
4.  Candidate Evidence Evaluation, Fusion Mind Level 1 assessment,
    shortlisting, and HR System write-back.

The model separates internal candidate identity from source-specific
records, preserves evidence provenance, versions role configurations,
and stores enough lineage to explain how a shortlist was produced.

## 2. Data Modelling Principles

1.  **Preserve source identity:** Store external requisition,
    application, candidate, source-profile, and assessment-session
    identifiers separately from internal IDs.
2.  **Keep provenance:** Every external profile field or evidence item
    should be traceable to its source and collection time where
    feasible.
3.  **Version configuration:** Role briefs, evaluation configurations,
    search policies, scoring rules, and prompts must be versioned.
4.  **Keep applicant and discovered records distinguishable:** Phase 3A
    applicants come from the HR System. Phase 3B candidates come from
    approved discovery sources.
5.  **Separate identity from source record:** One internal candidate may
    have several source records. Do not merge uncertain identity matches
    automatically.
6.  **Separate evidence from evaluation:** Evidence is the observed
    material; evaluation is the system's interpretation or score against
    a specific configuration version.
7.  **Separate assessment session from result:** Invitations/status and
    the final result have different lifecycles.
8.  **Audit decisions and changes:** Record approvals, manual overrides,
    state transitions, and write-back outcomes.
9.  **Minimize personal data:** Store only what is required, with
    controlled access and retention.
10. **Treat provider details as unknown until confirmed:** HR System and
    Fusion Mind fields/statuses must be mapped from official contracts,
    not guessed.

------------------------------------------------------------------------

## 3. Entity Relationship Overview

``` mermaid
erDiagram
    REQUISITION ||--o{ ROLE_BRIEF_VERSION : has
    ROLE_BRIEF_VERSION ||--o{ ROLE_CONFIGURATION_VERSION : configures
    REQUISITION ||--o{ SCREENING_RUN : processed_by
    SCREENING_RUN }o--|| ROLE_CONFIGURATION_VERSION : pins
    SCREENING_RUN ||--o{ CANDIDATE_SOURCE_RECORD : collects
    CANDIDATE ||--o{ CANDIDATE_SOURCE_RECORD : represented_by
    CANDIDATE_SOURCE_RECORD ||--o{ CANDIDATE_EVIDENCE : provides
    CANDIDATE ||--o{ CANDIDATE_EVALUATION : evaluated_in
    SCREENING_RUN ||--o{ CANDIDATE_EVALUATION : contains
    ROLE_CONFIGURATION_VERSION ||--o{ CANDIDATE_EVALUATION : governs
    CANDIDATE ||--o{ ASSESSMENT_SESSION : takes
    SCREENING_RUN ||--o{ ASSESSMENT_SESSION : schedules
    ASSESSMENT_SESSION ||--o{ ASSESSMENT_RESULT : returns
    SCREENING_RUN ||--o{ SHORTLIST : creates
    SHORTLIST ||--o{ SHORTLIST_ENTRY : contains
    CANDIDATE ||--o{ SHORTLIST_ENTRY : selected_as
    SCREENING_RUN ||--o{ DISCOVERY_BATCH : executes
    DISCOVERY_BATCH ||--o{ DISCOVERY_RESULT : finds
    CANDIDATE_SOURCE_RECORD ||--o{ DISCOVERY_RESULT : normalizes_to
    SCREENING_RUN ||--o{ INTEGRATION_ATTEMPT : records
    SCREENING_RUN ||--o{ AUDIT_EVENT : audits
```

The diagram is conceptual. The physical schema may add join tables,
event tables, provider payload tables, or separate version tables
depending on the selected database and implementation approach.

------------------------------------------------------------------------

## 4. Entity Catalogue

### 4.1 `requisition`

Represents the hiring request obtained from the HR System.

  --------------------------------------------------------------------------------------
  Attribute                   Type (logical)                Required Notes
  --------------------------- ---------------- --------------------- -------------------
  `id`                        UUID                               Yes Internal primary
                                                                     key

  `hr_system_key`             String                             Yes Identifies which HR
                                                                     System
                                                                     instance/provider
                                                                     owns the record

  `external_requisition_id`   String                             Yes HR System
                                                                     requisition
                                                                     identifier

  `external_version`          String /                            No Source version or
                              nullable                               ETag if available

  `source_status`             String                             Yes Original HR System
                                                                     status

  `last_source_modified_at`   Timestamp /                         No Source timestamp if
                              nullable                               provided

  `last_synced_at`            Timestamp                          Yes Last successful
                                                                     retrieval

  `created_at`                Timestamp                          Yes Internal creation
                                                                     time

  `updated_at`                Timestamp                          Yes Internal update
                                                                     time
  --------------------------------------------------------------------------------------

**Integrity:** Unique on `(hr_system_key, external_requisition_id)`.

### 4.2 `requisition_snapshot`

Stores a versioned source snapshot or secure reference to the
requisition data used by a screening run.

  -----------------------------------------------------------------------------
  Attribute             Type                          Required Notes
  --------------------- ---------------- --------------------- ----------------
  `id`                  UUID                               Yes Primary key

  `requisition_id`      UUID                               Yes FK to
                                                               `requisition`

  `external_version`    String /                            No Source version
                        nullable                               

  `payload_reference`   String                             Yes Secure
                                                               object-storage
                                                               reference or
                                                               encrypted
                                                               payload
                                                               reference

  `payload_hash`        String                             Yes Detects content
                                                               changes without
                                                               relying only on
                                                               timestamps

  `captured_at`         Timestamp                          Yes Snapshot time

  `schema_version`      String                             Yes Ingestion schema
                                                               version
  -----------------------------------------------------------------------------

### 4.3 `screening_run`

One execution of the screening workflow for a requisition.

  -----------------------------------------------------------------------------------------
  Attribute                         Type                          Required Notes
  --------------------------------- ---------------- --------------------- ----------------
  `id`                              UUID                               Yes Primary key

  `requisition_id`                  UUID                               Yes FK to
                                                                           requisition

  `requisition_snapshot_id`         UUID                               Yes Pinned source
                                                                           snapshot

  `role_brief_version_id`           UUID / nullable                     No Set once role
                                                                           brief is created

  `role_configuration_version_id`   UUID / nullable                     No Approved
                                                                           configuration
                                                                           used for this
                                                                           run

  `status`                          Enum/String                        Yes Workflow state

  `started_by`                      String /                            No User/service
                                    nullable                               identity

  `correlation_id`                  String                             Yes Cross-service
                                                                           trace identifier

  `started_at`                      Timestamp                          Yes Run start

  `completed_at`                    Timestamp /                         No Completion time
                                    nullable                               

  `completion_reason`               String /                            No Success, limited
                                    nullable                               discovery,
                                                                           blocked, etc.

  `created_at`                      Timestamp                          Yes Record creation
  -----------------------------------------------------------------------------------------

Suggested states: `created`, `ingesting_requisition`,
`role_brief_draft`, `awaiting_role_approval`, `role_configuration`,
`awaiting_configuration_approval`, `sourcing`, `candidate_pool_ready`,
`evaluating_profiles`, `assessment_processing`, `shortlist_ready`,
`writing_back_to_hr`, `completed`, `completed_with_exceptions`,
`blocked`, `cancelled`.

### 4.4 `role_brief_version`

An immutable, approved or draft structured representation of the role
requirements.

  --------------------------------------------------------------------------------------
  Attribute                 Type                          Required Notes
  ------------------------- ---------------- --------------------- ---------------------
  `id`                      UUID                               Yes Primary key

  `requisition_id`          UUID                               Yes FK to requisition

  `version_number`          Integer                            Yes Monotonically
                                                                   increasing per
                                                                   requisition

  `status`                  Enum/String                        Yes Draft, awaiting
                                                                   review, approved,
                                                                   superseded

  `structured_role_data`    JSONB                              Yes Role purpose,
                                                                   responsibilities,
                                                                   skills, level,
                                                                   constraints

  `explicit_source_facts`   JSONB                              Yes Facts directly
                                                                   supported by HR
                                                                   System source

  `ai_inferences`           JSONB                              Yes Proposed
                                                                   interpretation,
                                                                   clearly separated
                                                                   from source facts

  `ambiguities`             JSONB                              Yes Missing/conflicting
                                                                   information

  `source_snapshot_id`      UUID                               Yes Source lineage

  `schema_version`          String                             Yes Schema version

  `created_by`              String                             Yes User/service/model
                                                                   pipeline

  `approved_by`             String /                            No Approver identity
                            nullable                               

  `approved_at`             Timestamp /                         No Approval time
                            nullable                               

  `created_at`              Timestamp                          Yes Creation time
  --------------------------------------------------------------------------------------

**Integrity:** Unique on `(requisition_id, version_number)`. Approved
versions should not be edited in place.

### 4.5 `role_configuration_version`

The approved evaluation and search policy derived from a role brief.

  ---------------------------------------------------------------------------------------
  Attribute                       Type                          Required Notes
  ------------------------------- ---------------- --------------------- ----------------
  `id`                            UUID                               Yes Primary key

  `role_brief_version_id`         UUID                               Yes FK to role brief

  `version_number`                Integer                            Yes Version per role
                                                                         brief or
                                                                         requisition

  `status`                        Enum/String                        Yes Draft, awaiting
                                                                         approval,
                                                                         approved,
                                                                         superseded

  `mandatory_criteria`            JSONB                              Yes Eligibility
                                                                         gates and
                                                                         outcomes

  `preferred_criteria`            JSONB                              Yes Weighted or
                                                                         prioritized
                                                                         criteria

  `scoring_rubric`                JSONB                              Yes Criterion scales
                                                                         and score
                                                                         semantics

  `weights_and_thresholds`        JSONB                              Yes Approved weights
                                                                         and progression
                                                                         thresholds

  `evidence_rules`                JSONB                              Yes Acceptable
                                                                         evidence,
                                                                         quality,
                                                                         uncertainty
                                                                         rules

  `fusion_mind_assessment_plan`   JSONB                              Yes Planned Level 1
                                                                         assessment
                                                                         mapping

  `discovery_policy`              JSONB                              Yes Route families,
                                                                         budgets,
                                                                         stopping rules

  `prompt_versions`               JSONB                              Yes AI prompt/model
                                                                         identifiers used
                                                                         to generate
                                                                         configuration

  `schema_version`                String                             Yes Configuration
                                                                         schema version

  `approved_by`                   String /                            No Approver
                                  nullable                               

  `approved_at`                   Timestamp /                         No Approval time
                                  nullable                               

  `created_at`                    Timestamp                          Yes Creation time
  ---------------------------------------------------------------------------------------

**Integrity:** Approved configurations are immutable. A change creates a
new version.

### 4.6 `candidate`

Represents an internal candidate identity, which may be linked to
multiple source records.

  -----------------------------------------------------------------------------
  Attribute           Type                          Required Notes
  ------------------- ---------------- --------------------- ------------------
  `id`                UUID                               Yes Internal primary
                                                             key

  `identity_status`   Enum/String                        Yes Confirmed,
                                                             probable,
                                                             review_required,
                                                             unresolved

  `created_at`        Timestamp                          Yes Creation time

  `updated_at`        Timestamp                          Yes Last update
  -----------------------------------------------------------------------------

Do not make a name alone a unique identifier. Keep personally
identifying fields in access-controlled source records or a protected
profile table.

### 4.7 `candidate_source_record`

Represents a source-specific representation of a candidate.

  -------------------------------------------------------------------------------------------
  Attribute                    Type                          Required Notes
  ---------------------------- ---------------- --------------------- -----------------------
  `id`                         UUID                               Yes Primary key

  `candidate_id`               UUID / nullable                     No FK to candidate; null
                                                                      while unresolved if
                                                                      needed

  `screening_run_id`           UUID                               Yes FK to screening run

  `source_type`                Enum/String                        Yes `hr_applicant` or
                                                                      `proactive_discovery`

  `source_system_key`          String                             Yes HR provider or
                                                                      discovery source
                                                                      identifier

  `external_candidate_id`      String /                            No Source candidate ID
                               nullable                               

  `external_application_id`    String /                            No HR application ID for
                               nullable                               3A

  `source_profile_reference`   String /                            No Permitted profile
                               nullable                               URL/reference

  `payload_reference`          String /                            No Secure source snapshot
                               nullable                               reference

  `payload_hash`               String /                            No Detects changed source
                               nullable                               payload

  `collected_at`               Timestamp                          Yes Source collection time

  `last_verified_at`           Timestamp /                         No Last verification time
                               nullable                               

  `normalization_status`       Enum/String                        Yes Pending, normalized,
                                                                      failed, review_required

  `created_at`                 Timestamp                          Yes Creation time
  -------------------------------------------------------------------------------------------

**Integrity:** Add provider-specific unique constraints where stable IDs
exist. Do not assume an external candidate ID is globally unique across
providers.

### 4.8 `candidate_profile_field`

Optional normalized field table when field-level provenance is needed.

  ----------------------------------------------------------------------------------
  Attribute                Type                          Required Notes
  ------------------------ ---------------- --------------------- ------------------
  `id`                     UUID                               Yes Primary key

  `source_record_id`       UUID                               Yes FK to candidate
                                                                  source record

  `field_name`             String                             Yes e.g. title,
                                                                  skills, location

  `field_value`            JSONB / text                       Yes Normalized value

  `source_location`        String /                            No Where the value
                           nullable                               came from

  `provenance_reference`   String                             Yes Source
                                                                  payload/evidence
                                                                  reference

  `observed_at`            Timestamp                          Yes Observation time

  `normalizer_version`     String                             Yes Transformation
                                                                  version
  ----------------------------------------------------------------------------------

### 4.9 `candidate_evidence`

A piece of evidence used to evaluate a candidate against a criterion.

  ----------------------------------------------------------------------------------------
  Attribute                 Type                          Required Notes
  ------------------------- ---------------- --------------------- -----------------------
  `id`                      UUID                               Yes Primary key

  `candidate_id`            UUID                               Yes FK to candidate

  `source_record_id`        UUID                               Yes FK to source record

  `screening_run_id`        UUID                               Yes FK to screening run

  `criterion_key`           String /                            No Criterion from pinned
                            nullable                               configuration

  `evidence_type`           String                             Yes Skill, responsibility,
                                                                   project, qualification,
                                                                   outcome, etc.

  `evidence_summary`        Text                               Yes Concise evidence
                                                                   representation

  `source_location`         String /                            No Page, section, URL
                            nullable                               fragment, or source
                                                                   field

  `payload_reference`       String /                            No Link to secure original
                            nullable                               artifact

  `quality_indicator`       String /                            No Evidence quality
                            nullable                               assessment

  `uncertainty_indicator`   String /                            No Ambiguity/uncertainty
                            nullable                               marker

  `extraction_method`       String                             Yes Parser/model pipeline

  `prompt_version`          String /                            No Prompt used if AI
                            nullable                               assisted

  `created_at`              Timestamp                          Yes Evidence extraction
                                                                   time
  ----------------------------------------------------------------------------------------

Evidence records should be immutable for a given run. Re-extraction
creates a new evidence set or version, rather than silently changing
evidence behind a previous evaluation.

### 4.10 `discovery_query`

Represents a planned or executed proactive search route/query.

  ----------------------------------------------------------------------------------------------
  Attribute                         Type                          Required Notes
  --------------------------------- ---------------- --------------------- ---------------------
  `id`                              UUID                               Yes Primary key

  `screening_run_id`                UUID                               Yes FK to screening run

  `role_configuration_version_id`   UUID                               Yes Approved
                                                                           configuration

  `source_system_key`               String                             Yes Approved source

  `route_type`                      Enum/String                        Yes Direct,
                                                                           adjacent_role,
                                                                           capability_led,
                                                                           transferable_skill,
                                                                           other

  `query_reference`                 String /                            No Store raw query only
                                    nullable                               where permitted

  `query_hash`                      String /                            No Query identifier when
                                    nullable                               raw query should not
                                                                           be retained

  `route_rationale`                 Text                               Yes Why this route is
                                                                           relevant

  `batch_limit`                     Integer                            Yes Maximum results for
                                                                           this query batch

  `status`                          String                             Yes Planned, running,
                                                                           completed, failed,
                                                                           stopped

  `created_at`                      Timestamp                          Yes Creation time
  ----------------------------------------------------------------------------------------------

### 4.11 `discovery_batch`

A bounded execution of a search route.

  ---------------------------------------------------------------------------------------
  Attribute                      Type                          Required Notes
  ------------------------------ ---------------- --------------------- -----------------
  `id`                           UUID                               Yes Primary key

  `screening_run_id`             UUID                               Yes FK to run

  `discovery_query_id`           UUID                               Yes FK to query

  `batch_number`                 Integer                            Yes Sequence within
                                                                        query/route

  `source_cursor_reference`      String /                            No Pagination cursor
                                 nullable                               if permitted

  `requested_count`              Integer                            Yes Requested batch
                                                                        size

  `returned_count`               Integer                            Yes Results returned

  `new_unique_count`             Integer                            Yes New unique
                                                                        profiles

  `plausibly_relevant_count`     Integer /                           No Relevance yield
                                 nullable                               measure

  `estimated_evidence_quality`   String /                            No Aggregate
                                 nullable                               evidence quality

  `budget_units_used`            Numeric                            Yes Source
                                                                        calls/time/cost
                                                                        units

  `status`                       String                             Yes Completed,
                                                                        failed, partial

  `stop_or_adapt_reason`         String /                            No Budget,
                                 nullable                               diminishing
                                                                        returns, source
                                                                        limit, etc.

  `started_at`                   Timestamp                          Yes Start time

  `completed_at`                 Timestamp /                         No End time
                                 nullable                               
  ---------------------------------------------------------------------------------------

### 4.12 `discovery_result`

Represents a raw/normalized result returned by a proactive source.

  -------------------------------------------------------------------------------------------
  Attribute                      Type                          Required Notes
  ------------------------------ ---------------- --------------------- ---------------------
  `id`                           UUID                               Yes Primary key

  `discovery_batch_id`           UUID                               Yes FK to batch

  `candidate_source_record_id`   UUID / nullable                     No Result normalized to
                                                                        source record

  `external_result_id`           String /                            No Source result ID
                                 nullable                               

  `result_reference`             String /                            No Permitted source
                                 nullable                               reference

  `deduplication_status`         String                             Yes New, duplicate,
                                                                        possible_duplicate,
                                                                        ignored

  `relevance_label`              String /                            No Initial route
                                 nullable                               relevance label

  `created_at`                   Timestamp                          Yes Result ingestion time
  -------------------------------------------------------------------------------------------

### 4.13 `assessment_session`

Tracks Fusion Mind Level 1 assessment orchestration.

  --------------------------------------------------------------------------------------------------
  Attribute                              Type                          Required Notes
  -------------------------------------- ---------------- --------------------- --------------------
  `id`                                   UUID                               Yes Internal primary key

  `screening_run_id`                     UUID                               Yes FK to run

  `candidate_id`                         UUID                               Yes FK to candidate

  `candidate_source_record_id`           UUID / nullable                     No Source record used
                                                                                for provider mapping

  `provider_key`                         String                             Yes Fusion Mind provider
                                                                                identifier

  `provider_session_id`                  String /                            No External
                                         nullable                               session/invitation
                                                                                ID

  `assessment_configuration_reference`   String                             Yes Configured
                                                                                assessment/test
                                                                                reference

  `assessment_version`                   String /                            No Provider assessment
                                         nullable                               version

  `status`                               Enum/String                        Yes Internal assessment
                                                                                state

  `idempotency_key`                      String                             Yes Prevent duplicate
                                                                                session creation

  `invited_at`                           Timestamp /                         No Invitation time
                                         nullable                               

  `completed_at`                         Timestamp /                         No Completion time
                                         nullable                               

  `last_status_check_at`                 Timestamp /                         No Last polling/check
                                         nullable                               time

  `created_at`                           Timestamp                          Yes Creation time
  --------------------------------------------------------------------------------------------------

Suggested internal states: `not_required`, `pending_invitation`,
`invited`, `in_progress`, `completed`, `result_received`, `validated`,
`invalid_result`, `candidate_mapping_error`, `provider_error`,
`expired`, `manual_review`.

### 4.14 `assessment_result`

Stores validated result metadata and a protected reference to the
provider result payload.

  -------------------------------------------------------------------------------------
  Attribute                    Type                          Required Notes
  ---------------------------- ---------------- --------------------- -----------------
  `id`                         UUID                               Yes Primary key

  `assessment_session_id`      UUID                               Yes FK to session

  `provider_result_id`         String /                            No Provider result
                               nullable                               identifier

  `provider_result_version`    String /                            No Provider result
                               nullable                               version

  `result_status`              Enum/String                        Yes Received, valid,
                                                                      invalid,
                                                                      superseded,
                                                                      review_required

  `normalized_score_payload`   JSONB / nullable                    No Only approved
                                                                      normalized result
                                                                      fields

  `raw_payload_reference`      String /                            No Secure reference
                               nullable                               if retention is
                                                                      permitted

  `validation_status`          String                             Yes Pending, valid,
                                                                      invalid,
                                                                      review_required

  `validation_notes`           Text / nullable                     No Non-sensitive
                                                                      reason/details

  `received_at`                Timestamp                          Yes Receipt time

  `validated_at`               Timestamp /                         No Validation time
                               nullable                               
  -------------------------------------------------------------------------------------

Do not assume Fusion Mind returns one scalar score. Preserve the
provider result shape only as permitted, then map supported fields into
a documented normalized contract.

### 4.15 `candidate_evaluation`

One evaluation of a candidate for a specific screening run and
configuration version.

  ------------------------------------------------------------------------------------------
  Attribute                         Type                          Required Notes
  --------------------------------- ---------------- --------------------- -----------------
  `id`                              UUID                               Yes Primary key

  `screening_run_id`                UUID                               Yes FK to run

  `candidate_id`                    UUID                               Yes FK to candidate

  `role_configuration_version_id`   UUID                               Yes Configuration
                                                                           used

  `evaluation_version`              Integer                            Yes Incremented when
                                                                           re-evaluated

  `mandatory_gate_results`          JSONB                              Yes Per-gate result
                                                                           and rationale

  `profile_evidence_score`          Numeric /                           No Profile-based
                                    nullable                               score if
                                                                           configured

  `assessment_score`                Numeric /                           No Normalized
                                    nullable                               assessment score,
                                                                           if valid and
                                                                           applicable

  `combined_score`                  Numeric /                           No Only when
                                    nullable                               approved formula
                                                                           permits

  `criterion_breakdown`             JSONB                              Yes Criterion-level
                                                                           result and
                                                                           evidence
                                                                           references

  `evidence_completeness`           String /                            No Completeness
                                    nullable                               indicator

  `uncertainty_flags`               JSONB                              Yes Unknowns,
                                                                           conflicts, low
                                                                           evidence quality

  `recommendation`                  Enum/String                        Yes Shortlist, needs
                                                                           review, not
                                                                           shortlisted,
                                                                           pending

  `reason_codes`                    JSONB                              Yes Approved
                                                                           explanation codes

  `scoring_version`                 String                             Yes Deterministic
                                                                           scoring
                                                                           implementation
                                                                           version

  `created_at`                      Timestamp                          Yes Evaluation time
  ------------------------------------------------------------------------------------------

The final evaluation must reference the evidence set and configuration
version used. Do not overwrite a prior evaluation version.

### 4.16 `shortlist` and `shortlist_entry`

`shortlist` is a versioned snapshot for a run. `shortlist_entry` stores
one candidate outcome within it.

**`shortlist`** - `id` UUID primary key. - `screening_run_id` FK. -
`version_number`. - `status`. - `created_at`. - `created_by`. -
`writeback_status`. - `writeback_completed_at`.

**`shortlist_entry`** - `id` UUID primary key. - `shortlist_id` FK. -
`candidate_id` FK. - `candidate_source_record_id` nullable FK. -
`candidate_evaluation_id` FK. - `outcome` (`shortlist`, `needs_review`,
`not_shortlisted`, `assessment_pending`, `assessment_exception`). -
`rank` nullable, if ranking is approved. - `reason_codes`. -
`hr_external_candidate_id` nullable. - `hr_external_application_id`
nullable. - `writeback_status`. - `created_at`.

Do not force proactive candidates into an applicant-only schema. HR
System write-back may need a distinct pathway for non-applicants.

### 4.17 `integration_attempt`

Tracks external calls and retry behavior without logging secrets or
unnecessary personal data.

Attributes: - `id` - `screening_run_id` - `integration_name` -
`operation` - `correlation_id` - `idempotency_key` - `attempt_number` -
`request_reference` - `response_reference` - `http_status` where
applicable - `outcome` - `error_code` - `started_at` - `completed_at` -
`next_retry_at`

### 4.18 `audit_event`

Append-only record of important actions and decisions.

Attributes: - `id` - `screening_run_id` - `entity_type` - `entity_id` -
`event_type` - `actor_type` - `actor_id` nullable - `timestamp` -
`correlation_id` - `configuration_version_id` nullable - `reason_code`
nullable - `details_reference` nullable

Audit events should record configuration approvals, overrides, state
transitions, assessment result validation, shortlist creation, and HR
write-back outcomes.

------------------------------------------------------------------------

## 5. Relationship and Cardinality Rules

-   One requisition can have multiple source snapshots, role brief
    versions, and screening runs.
-   One screening run pins one requisition snapshot and, once approved,
    one role configuration version.
-   One role brief version can have multiple configuration versions.
-   One internal candidate can have multiple source records.
-   A source record belongs to a particular source and collection/run
    context.
-   One source record can provide multiple evidence items.
-   One candidate can have multiple evaluations across runs or
    configuration versions.
-   One candidate can have multiple assessment sessions across separate
    runs, but duplicate invitations for the same run/configuration
    should be prevented.
-   One assessment session may have multiple result records if the
    provider supports revisions; exactly one result should be designated
    current/valid for a session according to policy.
-   One shortlist contains multiple shortlist entries.
-   One shortlist entry points to the evaluation that justified the
    outcome.
-   One screening run can have many discovery queries, batches, and
    results.
-   One screening run can have many integration attempts and audit
    events.

------------------------------------------------------------------------

## 6. Keys, Constraints, and Indexes

### Unique constraints

Examples to validate against provider semantics: -
`(hr_system_key, external_requisition_id)` on requisition. -
`(requisition_id, version_number)` on role brief. -
`(role_brief_version_id, version_number)` on role configuration. -
`(screening_run_id, external_application_id)` for HR application imports
when application ID is stable. - `(provider_key, provider_session_id)`
for assessment sessions when non-null. - `(shortlist_id, candidate_id)`
on shortlist entries. -
`(screening_run_id, candidate_id, evaluation_version)` on candidate
evaluations.

### Indexes

-   `screening_run(requisition_id, status, started_at)`.
-   `candidate_source_record(screening_run_id, source_type)`.
-   `candidate_source_record(source_system_key, external_candidate_id)`.
-   `candidate_evidence(candidate_id, screening_run_id, criterion_key)`.
-   `assessment_session(provider_key, provider_session_id, status)`.
-   `candidate_evaluation(screening_run_id, recommendation)`.
-   `discovery_batch(screening_run_id, status)`.
-   `integration_attempt(screening_run_id, integration_name, outcome)`.
-   `audit_event(screening_run_id, timestamp)`.

Use JSONB for flexible structured payloads where fields evolve, but keep
high-value query/filter fields as typed columns. Avoid placing the
entire system model in one giant JSON document.

------------------------------------------------------------------------

## 7. State and Status Models

### 7.1 Screening run

`created`, `ingesting_requisition`, `role_brief_draft`,
`awaiting_role_approval`, `role_configuration`,
`awaiting_configuration_approval`, `sourcing`, `candidate_pool_ready`,
`evaluating_profiles`, `assessment_processing`, `shortlist_ready`,
`writing_back_to_hr`, `completed`, `completed_with_exceptions`,
`blocked`, `cancelled`.

### 7.2 Candidate source record

`received`, `normalizing`, `normalized`, `normalization_failed`,
`duplicate_review`, `ready_for_evaluation`, `held_for_data_quality`.

### 7.3 Discovery

Query: `planned`, `running`, `completed`, `failed`, `stopped`.\
Batch: `running`, `completed`, `partial`, `failed`.\
Stop reasons: `target_met`, `diminishing_returns`,
`hard_budget_reached`, `source_limit`, `policy_stop`, `source_failure`.

### 7.4 Assessment

`not_required`, `pending_invitation`, `invited`, `in_progress`,
`completed`, `result_received`, `validated`, `invalid_result`,
`candidate_mapping_error`, `provider_error`, `expired`, `manual_review`.

### 7.5 Evaluation and shortlist

`shortlist`, `needs_review`, `not_shortlisted`, `assessment_pending`,
`assessment_exception`.

These are proposed internal values. Map them to the actual HR System and
Fusion Mind status vocabularies after reviewing provider contracts.

------------------------------------------------------------------------

## 8. Data Lineage and Reproducibility

For every final candidate evaluation, preserve: - HR requisition ID and
source snapshot/version. - Role brief version. - Role configuration
version. - Candidate source record IDs. - Evidence IDs and source
references. - AI prompt/model versions used for extraction or
interpretation. - Scoring implementation version. - Fusion Mind
session/result IDs and assessment version, if applicable. - Evaluation
version and timestamp. - Shortlist version and write-back result.

This makes the shortlist explainable and supports controlled
re-evaluation when source data or configuration changes.

------------------------------------------------------------------------

## 9. Privacy, Retention, and Access

-   Define which candidate fields are needed and why.
-   Keep sensitive contact details in restricted tables or protected
    source payloads.
-   Apply role-based access and field-level restrictions.
-   Encrypt database, object storage, and transport.
-   Avoid raw candidate content in application logs.
-   Define retention by source, data type, and legal/business purpose.
-   Honor source-provider restrictions and deletion obligations.
-   Do not infer or store sensitive personal attributes for scoring.
-   Restrict access to raw Fusion Mind results to authorized roles.
-   Ensure deletion requests propagate to derived records according to
    approved retention/legal policy while preserving any audit records
    legally required.

Exact retention durations and lawful basis are policy decisions and are
not specified by this logical model.

------------------------------------------------------------------------

## 10. Open Data Decisions

1.  Which HR System and exact requisition/application/candidate IDs are
    available?
2.  Can HR System applicants and proactive candidates be represented in
    one candidate entity or require separate write-back flows?
3.  What candidate fields can be retrieved and written back?
4.  Does Fusion Mind expose stable session/result IDs and versioned
    results?
5.  Does Fusion Mind return scalar scores, sub-scores, bands, or
    detailed responses?
6.  Which source-profile fields may be retained and for how long?
7.  What identity-resolution fields are permitted?
8.  What evaluation results and rationale can be written to the HR
    System?
9.  Are audit events required to be immutable/tamper-evident under
    organizational policy?
10. What retention/deletion and candidate-access policies apply?

------------------------------------------------------------------------

## 11. Implementation Guidance

Implement the model incrementally: 1. Requisition, snapshot, screening
run, role brief, and configuration version. 2. Candidate, source record,
and Phase 3A applicant import. 3. Discovery query, batch, and result
records for Phase 3B. 4. Evidence and evaluation records. 5. Fusion Mind
assessment session and result records. 6. Shortlist, shortlist entry,
and HR write-back tracking. 7. Audit events, constraints, indexes, and
retention automation.

Begin with the entities required for traceability and idempotency. Add
field-level normalization or specialized search storage only when
requirements justify the added complexity.

## 12. Summary

The data model is centered on a versioned `screening_run` that pins the
requisition snapshot and approved role configuration. Phase 3A
applicants and Phase 3B discoveries are stored as distinct source
records and then mapped into a unified candidate identity where
supported. Candidate evidence is stored separately from evaluation
results. Fusion Mind sessions and results have their own lifecycle and
validation. A versioned shortlist records which candidate evaluations
justified each outcome and tracks write-back to the HR System.

**Core lineage:** HR requisition snapshot → role brief version → role
configuration version → screening run → candidate source records →
candidate evidence → candidate evaluation → Fusion Mind assessment
result where applicable → shortlist entry → HR System write-back.
