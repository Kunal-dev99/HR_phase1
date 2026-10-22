# AI-Enabled Recruitment Screening System

## Detailed Technical Architecture: Phases 1--4

**Document status:** Proposed technical architecture for review\
**Scope:** HR System requisition ingestion through final shortlist
write-back\
**Third-party assessment:** Fusion Mind, Level 1 assessment only\
**Important:** Technology choices and API contracts below are
recommendations, not confirmed existing capabilities. Validate them
against organizational standards and the HR System/Fusion Mind
documentation before implementation.

------------------------------------------------------------------------

## 1. Purpose and Scope

This document translates the conceptual system design into a proposed
technical architecture. It describes application modules, runtime
responsibilities, data storage, APIs, workflow execution, integrations,
security, deployment, and implementation sequencing.

### In scope

1.  Job Requirement Understanding.
2.  Role & Assessment Intelligence.
3.  Candidate Sourcing:
    -   3A Applicant-led Recruitment, where the HR System supplies the
        existing applicant list.
    -   3B Proactive Talent Discovery, using approved source connectors.
4.  Candidate Evidence Evaluation, Fusion Mind Level 1 assessment
    integration, shortlisting, and write-back to the HR System.

### Out of scope

Human interview orchestration, final hiring decisions, offer management,
onboarding, and post-hire learning.

### Architecture principles

-   Start with a **modular application**, not a microservice per logical
    component.
-   Keep external systems behind adapters.
-   Separate AI interpretation from deterministic policy and scoring.
-   Use asynchronous, durable workflows for long-running sourcing and
    assessment activities.
-   Version role configurations and evaluation runs.
-   Preserve evidence provenance and audit history.
-   Make integrations idempotent and retryable.
-   Use only approved data sources and authorized collection methods.

------------------------------------------------------------------------

## 2. Proposed Technology Baseline

These are starting recommendations, not mandated choices.

  -----------------------------------------------------------------------
  Area                    Proposed baseline       Rationale
  ----------------------- ----------------------- -----------------------
  Frontend/review UI      React + TypeScript      Structured review
                                                  screens and operational
                                                  dashboards

  Backend API             Python + FastAPI        Strong fit for document
                                                  processing, AI
                                                  orchestration, and
                                                  typed APIs

  Background processing   Celery/RQ with Redis,   Long-running jobs,
                          or a durable workflow   retries, batch
                          engine                  processing

  Durable workflow option Temporal or equivalent  Durable orchestration
                          if workflow complexity  of multi-step processes
                          warrants it             and external waits

  Primary database        PostgreSQL              Relational state,
                                                  configuration
                                                  versioning,
                                                  transactions, audit
                                                  references

  Object/document storage Approved object         Secure storage for
                          storage, such as        documents and derived
                          S3-compatible storage   artifacts where
                          or Azure Blob Storage   retention permits

  Search index            PostgreSQL full-text    Avoid premature
                          initially; dedicated    infrastructure
                          search engine only if   
                          needed                  

  Vector search           Optional pgvector or    Use only if semantic
                          managed vector store    retrieval materially
                                                  improves
                                                  discovery/evidence
                                                  search

  AI integration          Provider-neutral model  Centralized prompt
                          gateway/service wrapper versions, model
                                                  routing, structured
                                                  output validation

  Queue/cache             Redis or cloud-managed  Background jobs,
                          queue, selected to      throttling, short-lived
                          match workflow stack    coordination

  Secrets                 Cloud secret manager or Protect API credentials
                          organization-approved   
                          equivalent              

  Observability           Structured logs,        Operational visibility
                          metrics, traces, error  and audit correlation
                          reporting               

  Deployment              Containers on           Repeatable deployments
                          organization-approved   and horizontal scaling
                          cloud/container         
                          platform                
  -----------------------------------------------------------------------

Do not adopt every technology in the table automatically. Select the
smallest stack that meets throughput, reliability, security, and
organizational requirements.

------------------------------------------------------------------------

## 3. System Context

``` text
                         ┌─────────────────────────────┐
                         │ External HR System          │
                         │ Requisitions + applicants   │
                         │ Shortlist/status destination│
                         └──────────────┬──────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────┐
│             AI-Enabled Recruitment Screening Platform            │
│                                                                 │
│  ┌──────────────────┐    ┌───────────────────────────────────┐  │
│  │ Web UI / Review  │───▶│ API Gateway / FastAPI Application │  │
│  └──────────────────┘    └────────────────┬──────────────────┘  │
│                                           │                     │
│                             ┌─────────────▼────────────┐        │
│                             │ Workflow Orchestrator     │        │
│                             └─────────────┬────────────┘        │
│                                           │                     │
│      ┌────────────────┬──────────────────┼────────────────┐    │
│      ▼                ▼                  ▼                ▼    │
│  Phase 1/2        Phase 3A            Phase 3B          Phase 4 │
│  Role services    HR applicants      Discovery         Evidence │
│                                      service           evaluation│
│                                                           │     │
│                                           ┌───────────────┘     │
│                                           ▼                     │
│                                 ┌──────────────────────┐        │
│                                 │ Fusion Mind Adapter  │        │
│                                 └──────────┬───────────┘        │
│                                            │                    │
│  ┌───────────────────┐  ┌─────────────────▼─────────────────┐  │
│  │ PostgreSQL        │  │ Approved source connectors         │  │
│  │ Object storage    │  │ HR System / Fusion Mind adapters   │  │
│  │ Audit/event store │  └────────────────────────────────────┘  │
│  └───────────────────┘                                         │
└─────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
                         ┌─────────────────────────────┐
                         │ HR System shortlist update  │
                         └─────────────────────────────┘
```

The diagram is logical. It does not imply every box must be a separately
deployed service.

------------------------------------------------------------------------

## 4. Application Architecture

### 4.1 API and application layer

Responsibilities: - Authenticate users and service-to-service
requests. - Validate request schemas and permissions. - Create screening
runs and expose their status. - Start workflows rather than executing
long jobs inside HTTP requests. - Expose review, approval, evaluation,
and shortlist endpoints. - Enforce tenant/requisition access boundaries
if the system serves multiple business units.

The API should return a run identifier for long-running work. Clients
poll or subscribe to status updates rather than holding an HTTP request
open while sourcing, parsing documents, or waiting for Fusion Mind.

### 4.2 Workflow orchestrator

Responsibilities: - Sequence phases and enforce prerequisites. - Track
the current state of each screening run. - Persist checkpoints and
correlation IDs. - Schedule retries with bounded backoff. - Wait for
external events such as assessment completion. - Route errors to retry,
exception, or human-review states. - Resume safely after worker
restarts.

A durable workflow engine is useful if many runs wait hours or days for
assessments. For a smaller first release, a database-backed state
machine plus queue workers may be sufficient.

### 4.3 Domain modules

Use explicit module boundaries:

-   `requisitions`: HR System requisition retrieval and role input
    snapshots.
-   `role_briefs`: parsing, structured brief, ambiguity and approval
    workflow.
-   `role_models`: criteria, gates, weights, rubrics, thresholds,
    versioning.
-   `applicants`: Phase 3A import and application linkage.
-   `discovery`: Phase 3B query routes, budget, source results, stopping
    rules.
-   `identity`: candidate/source records and duplicate resolution.
-   `evidence`: document extraction, evidence records, criterion
    mapping.
-   `assessment`: Fusion Mind sessions, results, validation, score
    mapping.
-   `evaluation`: deterministic scoring, gates, uncertainty,
    explanations.
-   `shortlists`: progression rules, shortlist snapshots, HR write-back.
-   `audit`: append-only workflow and administrative events.
-   `integrations`: adapters and provider-specific schemas.

Keep scoring rules in normal application code or a versioned rules
module, not embedded only in AI prompts.

------------------------------------------------------------------------

## 5. Phase-by-Phase Runtime Design

## 5.1 Phase 1: Job Requirement Understanding

### Runtime sequence

1.  Workflow requests the requisition through `HRSystemAdapter`.
2.  Adapter authenticates, fetches the requisition, handles pagination
    if needed, and validates the response.
3.  Store a source snapshot or a secure reference to it, plus the
    external version/timestamp.
4.  Document/field parser extracts structured fields.
5.  AI role interpreter returns schema-constrained JSON:
    responsibilities, skills, seniority, constraints, outcomes,
    ambiguities, and suggested clarifying questions.
6.  Application validates the output against a versioned schema.
7.  Deterministic validation checks required fields and policy
    constraints.
8.  If material ambiguity remains, set `awaiting_role_review`; otherwise
    prepare the role brief for approval.
9.  Approved role brief is stored as an immutable version and linked to
    the requisition.

### Example structured output

``` json
{
  "role_title": "Example role",
  "responsibilities": [],
  "required_capabilities": [],
  "preferred_capabilities": [],
  "seniority": null,
  "location_constraints": [],
  "employment_constraints": [],
  "explicit_source_facts": [],
  "ai_inferences": [],
  "ambiguities": [],
  "source_references": [],
  "schema_version": "1.0"
}
```

This is illustrative only. The schema should be defined with business
stakeholders.

### Design controls

-   Preserve source text and provenance.
-   Label inferred content separately from source facts.
-   Do not let the model invent mandatory requirements.
-   Keep model prompts and extraction schema versioned.
-   Re-run parsing when the requisition source version changes, subject
    to run policy.

## 5.2 Phase 2: Role & Assessment Intelligence

### Runtime sequence

1.  Consume the approved role brief.
2.  AI proposes a role capability model and candidate evidence mappings.
3.  Deterministic rules validate the schema and allowed criterion types.
4.  Build mandatory gates separately from weighted criteria.
5.  Validate weights, thresholds, and scoring completeness.
6.  Select candidate Level 1 assessment(s) from the available Fusion
    Mind catalogue once the provider contract is known.
7.  Generate Phase 3B search routes from direct, adjacent, and
    capability-led strategies.
8.  Create a configuration version.
9.  Obtain approval according to policy and pin the version to the
    screening run.

### Configuration structure

A configuration should include: - Role brief version. - Mandatory gates
and outcomes. - Criteria, weights, rubrics, and evidence rules. -
Scoring thresholds and shortlist progression policy. - Fusion Mind
assessment mapping and required-result policy. - Discovery route
families, initial/expansion/hard budgets, and stopping rules. -
Prompt/model versions used to create the proposal. - Approval status,
approver, and timestamp.

### Important rule

A role configuration becomes immutable once a run begins evaluating
candidates. A material role change creates a new configuration version.
Do not silently adjust weights after seeing the candidate pool.

## 5.3 Phase 3A: Applicant-led Recruitment

### Runtime sequence

1.  Fetch applicant list for the requisition from the HR System.
2.  Paginate until the source indicates completion or an agreed cap is
    reached.
3.  Store external candidate/application IDs and source payload
    references.
4.  Normalize names, contact identifiers, profile fields, and
    resume/document references as permitted.
5.  Create or link candidate source records.
6.  Deduplicate using strong IDs first; use fuzzy matching only as a
    review signal.
7.  Mark data-quality problems and candidates ready for evaluation.

### Controls

-   Never reinterpret HR applicants as proactive discoveries.
-   Preserve HR System identifiers to enable safe write-back.
-   Use idempotency based on requisition ID, application ID, and source
    version.
-   Avoid storing unnecessary copies of contact data.
-   Respect HR System deletion/update semantics.

## 5.4 Phase 3B: Proactive Talent Discovery

### Runtime sequence

1.  Read the approved role configuration and source allowlist.
2.  Generate a search portfolio: direct matches, adjacent roles,
    capability-led queries, and transferable-skill routes.
3.  Execute a bounded batch through each permitted source adapter.
4.  Normalize results and preserve source/query provenance.
5.  Deduplicate against earlier results and, where permitted, the Phase
    3A pool.
6.  Measure relevance yield, unique candidates, route diversity,
    evidence completeness, and marginal yield.
7.  Select the next route/batch or stop according to deterministic
    policy.
8.  Persist a completion reason: target met, diminishing returns, hard
    budget reached, source limit, or failure.
9.  Mark discovered candidates as `proactive_discovery`.

### Adaptive controller

AI can recommend which route to try next, but deterministic code
enforces: - Source allowlist. - Initial and expansion budgets. - Hard
maximum. - Per-source limits. - Stop conditions. - Duplicate rules. -
Audit logging.

Keep an exploration reserve for alternative routes so a successful
direct search does not eliminate exploration of nontraditional
candidates.

### Retrieval design

Start with query expansion plus bounded retrieval and relevance
feedback. Add contextual bandit optimization only after sufficient
reliable feedback data exists. Do not make the first release dependent
on a learned policy without evaluation history.

## 5.5 Candidate identity resolution

Maintain separate entities for: - Internal candidate identity. -
Source-specific profile/application record. - Evidence items from each
source.

Use deterministic matching on authorized stable identifiers where
possible. Fuzzy match features may include normalized names, email or
phone hashes where lawful, profile URLs, and employment history, but
uncertain matches should not be auto-merged. The exact fields and
thresholds require privacy and data-owner approval.

Never overwrite the HR System's canonical candidate fields with
third-party values without an explicit merge policy.

## 5.6 Phase 4: Evidence Evaluation and Fusion Mind

### Profile evidence pipeline

1.  Fetch or read permitted candidate documents.
2.  Extract text and metadata using format-specific parsers.
3.  Normalize evidence into a candidate evidence schema.
4.  AI maps evidence to approved criteria and returns references plus
    uncertainty.
5.  Validate schema and evidence references.
6.  Deterministic evaluator calculates gate outcomes and weighted
    profile score.
7.  Decide whether Level 1 assessment is required by the approved
    assessment plan.

### Scoring pipeline

Keep independent outputs for: - Mandatory gate results. -
Profile-evidence score. - Fusion Mind assessment result/score. -
Evidence completeness/quality. - Uncertainty and review flags. - Final
progression recommendation.

Combine values only through an approved, versioned formula. Do not allow
the AI model to invent a final score or alter thresholds.

### Fusion Mind adapter sequence

1.  Create an internal assessment session record.
2.  Map internal candidate/requisition/configuration to provider fields.
3.  Submit invitation/session creation through the supported API or
    approved mechanism.
4.  Persist the provider session ID and request correlation ID.
5.  Track state through webhooks where supported, otherwise scheduled
    polling.
6.  Retrieve the final result.
7.  Validate provider result ID, session mapping, candidate mapping,
    assessment version, and finality.
8.  Persist raw/normalized result references according to retention
    policy.
9.  Map provider scores to approved criterion/result fields.
10. Trigger reevaluation.

The provider's actual integration capabilities are unconfirmed. Do not
finalize endpoint names or payloads until Fusion Mind documentation is
available.

### Failure policy

-   Provider error does not mean candidate failure.
-   Missing score does not become zero.
-   Duplicate callbacks must be idempotent.
-   Invalid or mismatched results enter review.
-   If an assessment is required for progression, mark the candidate
    `assessment_pending` or `assessment_exception` until resolved.

## 5.7 Shortlist and HR System write-back

1.  Create a versioned shortlist snapshot.
2.  Validate each shortlist entry against the configured progression
    policy.
3.  Build a minimal write-back payload supported by the HR System.
4.  Submit through `HRSystemAdapter`.
5.  Store request correlation ID, response status, and retry count.
6.  Retry transient failures safely.
7.  Reconcile internally shortlisted candidates with HR System records.
8.  Mark the run `completed` only when the agreed write-back criteria
    are met; otherwise use `completed_with_exceptions`.

For proactive candidates, first confirm how the HR System represents
non-applicants. The write-back path may differ from applicant updates.

------------------------------------------------------------------------

## 6. API Design

The following are proposed internal API shapes, not external provider
contracts.

### 6.1 Internal endpoints

  ---------------------------------------------------------------------------------------------------------
  Method                  Example route                                             Purpose
  ----------------------- --------------------------------------------------------- -----------------------
  POST                    `/api/v1/screening-runs`                                  Start a screening run
                                                                                    for a requisition

  GET                     `/api/v1/screening-runs/{run_id}`                         Get run state and phase
                                                                                    status

  POST                    `/api/v1/screening-runs/{run_id}/approve-role-brief`      Approve Phase 1 output

  POST                    `/api/v1/screening-runs/{run_id}/approve-configuration`   Approve Phase 2
                                                                                    configuration

  GET                     `/api/v1/screening-runs/{run_id}/candidates`              Browse unified
                                                                                    candidate pool

  GET                     `/api/v1/candidates/{candidate_id}/evaluation`            Retrieve evidence and
                                                                                    evaluation

  GET                     `/api/v1/screening-runs/{run_id}/shortlist`               Retrieve final
                                                                                    shortlist

  POST                    `/api/v1/screening-runs/{run_id}/retry-writeback`         Retry failed HR
                                                                                    write-back

  POST                    `/api/v1/webhooks/fusion-mind`                            Receive provider
                                                                                    callback if supported
  ---------------------------------------------------------------------------------------------------------

### 6.2 API conventions

-   Use request/response schemas with explicit versioning.
-   Return `202 Accepted` for asynchronous work, with `run_id` and
    status URL.
-   Require authorization for approvals and sensitive candidate data.
-   Include correlation IDs in responses and logs.
-   Support pagination on candidate lists.
-   Apply rate limiting and request-size limits.
-   Never expose provider credentials or raw sensitive payloads in logs.

### 6.3 External adapter contracts

Define internal interfaces first, then implement each provider adapter
against its official documentation: -
`HRSystemAdapter.get_requisition(requisition_id)` -
`HRSystemAdapter.list_applicants(requisition_id, cursor)` -
`HRSystemAdapter.get_candidate(candidate_id)` -
`HRSystemAdapter.write_shortlist(payload, idempotency_key)` -
`FusionMindAdapter.create_assessment(candidate_ref, assessment_config)` -
`FusionMindAdapter.get_status(provider_session_id)` -
`FusionMindAdapter.get_result(provider_session_id)` -
`DiscoverySourceAdapter.search(query, cursor, limits)`

These method names are examples for design discussion, not committed
signatures.

------------------------------------------------------------------------

## 7. Data Architecture

### 7.1 Storage responsibilities

**PostgreSQL** - Screening runs and state. - Requisition
snapshots/metadata. - Role briefs and configuration versions. -
Candidate identities and source records. - Evidence metadata and
references. - Assessment sessions/results metadata. - Evaluation and
shortlist records. - Integration attempts and audit references.

**Object storage** - Resumes, permitted source artifacts, extracted
text, and reports where necessary. - Encrypt and apply per-object access
controls. - Store references in PostgreSQL rather than large binary
content. - Apply retention/deletion policies by source and data type.

**Queue/workflow store** - Background task dispatch. - Workflow
checkpoints and pending external events. - Retry and dead-letter
handling, depending on selected technology.

**Search index** - Begin with PostgreSQL full-text or source-provided
search. - Add a dedicated search engine only if candidate corpus size,
ranking requirements, or latency justify it. - Use vector search as a
complement, not a replacement for exact filtering and eligibility rules.

### 7.2 Suggested table groups

-   `screening_runs`
-   `requisitions`
-   `role_briefs`
-   `role_configurations`
-   `candidates`
-   `candidate_source_records`
-   `candidate_evidence`
-   `discovery_queries`
-   `discovery_batches`
-   `assessment_sessions`
-   `assessment_results`
-   `candidate_evaluations`
-   `shortlists`
-   `integration_attempts`
-   `workflow_events`
-   `audit_events`

Use foreign keys, unique constraints, and indexes for requisition IDs,
source IDs, candidate IDs, run state, provider session IDs, and
timestamps. Exact schema should be designed from actual integration
payloads.

### 7.3 Data versioning

Every evaluation should reference: - HR requisition source version. -
Approved role brief version. - Role evaluation configuration version. -
Candidate evidence snapshot or evidence IDs. - Fusion Mind assessment
configuration/version. - Scoring implementation version. - AI
prompt/model version for extracted or interpreted evidence.

This makes a shortlist reproducible and helps explain why a candidate
received a particular outcome.

------------------------------------------------------------------------

## 8. Workflow State Machine and Events

### 8.1 Run states

Suggested states: `created`, `ingesting_requisition`,
`role_brief_draft`, `awaiting_role_approval`, `role_configuration`,
`awaiting_configuration_approval`, `sourcing`, `candidate_pool_ready`,
`evaluating_profiles`, `assessment_processing`, `shortlist_ready`,
`writing_back_to_hr`, `completed`, `completed_with_exceptions`,
`blocked`, `cancelled`.

### 8.2 Event examples

-   `RequisitionFetched`
-   `RoleBriefCreated`
-   `RoleBriefApproved`
-   `RoleConfigurationCreated`
-   `RoleConfigurationApproved`
-   `ApplicantBatchImported`
-   `DiscoveryBatchCompleted`
-   `CandidateIdentityResolved`
-   `CandidateEvidenceExtracted`
-   `AssessmentInvitationCreated`
-   `AssessmentResultReceived`
-   `AssessmentResultValidated`
-   `CandidateEvaluated`
-   `ShortlistCreated`
-   `HRWritebackSucceeded`
-   `HRWritebackFailed`

Use a transactional outbox pattern if a database state change must
reliably trigger a queue event. Make consumers idempotent. Keep audit
events append-only or otherwise tamper-evident according to
organizational standards.

------------------------------------------------------------------------

## 9. Security and Governance Architecture

### Identity and access

-   Use organization-approved SSO for human users.
-   Apply role-based access to requisitions, candidate records,
    configuration approvals, and reports.
-   Use separate service identities for HR System, Fusion Mind, and each
    discovery source.
-   Store secrets in a secret manager and rotate them.
-   Apply least privilege and environment separation.

### Data protection

-   TLS for all integrations.
-   Encryption at rest for databases and object storage.
-   Redact personal data from operational logs.
-   Use secure document parsing and malware scanning where required.
-   Keep data retention/deletion policies explicit.
-   Prevent candidate-supplied text from being treated as instructions
    to AI tools.

### AI governance

-   Use structured outputs and schema validation.
-   Version prompts and models.
-   Maintain evidence references for material claims.
-   Separate AI suggestions from approved policy.
-   Prevent AI from changing scoring weights, thresholds, or gate
    definitions at runtime.
-   Provide a review path for uncertainty, contradictions, and anomalous
    results.
-   Evaluate for disparate errors and job-related validity before broad
    deployment.

### Audit

Record actor, timestamp, correlation ID, configuration version,
data/source references, state transitions, approvals, overrides, and
write-back outcomes.

------------------------------------------------------------------------

## 10. Observability and Operational Support

### Metrics

-   Requisition ingestion success/failure and latency.
-   Applicant import count and pagination errors.
-   Discovery batch count, source yield, unique yield, budget consumed,
    stop reason.
-   Duplicate and uncertain identity-match rates.
-   Document parsing success and extraction quality.
-   Candidate evaluation duration and exception count.
-   Fusion Mind invitation, completion, result-validation, and
    provider-error rates.
-   Shortlist count and HR write-back success/failure.
-   Human review queue size and age.

### Logs and traces

-   Structured logs with `screening_run_id`, `requisition_id`,
    `candidate_id` where appropriate, `correlation_id`, and
    `integration_name`.
-   Avoid raw resumes, tokens, credentials, and unnecessary personal
    data in logs.
-   Trace calls across API, worker, database, and external adapters.

### Alerts

-   Repeated HR System/Fusion Mind failures.
-   Stuck workflow or assessment states.
-   Abnormal invalid-result rate.
-   Repeated write-back failures.
-   Search budget exhaustion with insufficient candidate yield.
-   Elevated parsing failures or identity-merge anomalies.

------------------------------------------------------------------------

## 11. Deployment Topology

### Initial production topology

-   **Web/API container:** stateless FastAPI application.
-   **Worker containers:** document processing, discovery, evaluation,
    and assessment tasks.
-   **Workflow/queue infrastructure:** selected durable workflow engine
    or managed queue.
-   **PostgreSQL:** managed relational database with backups and
    restricted network access.
-   **Object storage:** private buckets/containers, encryption,
    lifecycle policies.
-   **Secret manager:** integration credentials and model-provider keys.
-   **Monitoring platform:** logs, metrics, tracing, alerts.
-   **Optional search service:** only if scale/quality requirements
    justify it.

Deploy in private network segments where possible. External egress
should be restricted to approved model endpoints and approved
integrations. The exact cloud and network layout depends on the
organization's hosting policy.

### Environment strategy

1.  Development: synthetic/anonymized data and mocked external systems.
2.  Integration test: sandbox HR System and Fusion Mind, plus approved
    source test accounts.
3.  Staging: production-like configuration and access controls.
4.  Production: approved connectors, monitoring, backup, retention,
    incident ownership.

------------------------------------------------------------------------

## 12. Failure Handling and Resilience

  -----------------------------------------------------------------------
  Failure                             Required behavior
  ----------------------------------- -----------------------------------
  HR System unavailable               Retry boundedly; hold run if
                                      requisition/applicant data cannot
                                      be fetched

  Requisition changes mid-run         Detect source-version change;
                                      refresh or continue against pinned
                                      snapshot according to policy

  AI output invalid schema            Retry once or use controlled
                                      fallback; never accept invalid
                                      output silently

  Source connector fails              Retry within limits; record route
                                      failure and continue other
                                      permitted routes where appropriate

  Search budget exhausted             Stop; report target met or limited
                                      discovery accurately

  Duplicate identity uncertain        Keep records separate or send to
                                      review

  Fusion Mind unavailable             Retry; hold assessment-dependent
                                      progression without treating
                                      candidate as failed

  Assessment result mismatched        Quarantine result and send to
                                      review

  Duplicate provider callback         Idempotently ignore or reconcile

  HR write-back fails                 Keep shortlist internally; retry
                                      safely and mark run with exception

  Worker crashes                      Resume from durable workflow
                                      checkpoint

  Document cannot be parsed           Mark evidence incomplete and route
                                      according to policy
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## 13. Testing Strategy

### Unit

-   Role schema extraction and validation.
-   Mandatory gates and score calculation.
-   Candidate normalization and deduplication.
-   Search budget and stop conditions.
-   Fusion Mind result/status mapping.
-   HR write-back mapping and idempotency.

### Integration

-   HR requisition and applicant pagination.
-   Authentication/permission failures.
-   Fusion Mind invitation, callback/polling, result retrieval, and
    provider errors.
-   Approved source adapters and rate-limit handling.
-   Object storage permissions and retention behavior.

### End-to-end

-   Applicant-only path.
-   Proactive discovery path.
-   Combined path with overlapping profiles.
-   Required assessment pending/completed/invalid.
-   Requisition updated during run.
-   HR write-back outage after shortlist creation.
-   Manual review and approval path.
-   Cancellation and retry.

### Evaluation quality

-   Human-reviewed sample for role brief accuracy.
-   Evidence extraction precision/recall or rubric-based quality.
-   Criterion mapping quality.
-   Score calibration and consistency.
-   Search relevance, diversity, and marginal yield.
-   Fairness and error analysis.
-   Shortlist auditability and reproducibility.

------------------------------------------------------------------------

## 14. Implementation Plan

### Step 1: Integration discovery

Obtain official HR System and Fusion Mind documentation, credentials for
test environments, data contracts, source-use approvals, status
mappings, and retention requirements.

### Step 2: Foundation

Create API, database schema, workflow state machine, audit model,
secrets management, logging, and test harness.

### Step 3: Phases 1--2

Implement requisition ingestion, role brief extraction/review, role
configuration, validation, and versioning.

### Step 4: Phase 3A

Implement applicant ingestion, normalization, candidate/source records,
deduplication, and pagination.

### Step 5: Phase 3B

Implement approved source adapters, search route generation, batch
metrics, adaptive budget, and stopping rules.

### Step 6: Phase 4 profile evaluation

Implement document extraction, evidence mapping, deterministic
gates/scoring, uncertainty, and reports.

### Step 7: Fusion Mind integration

Implement invitation orchestration, status updates, result retrieval,
validation, and result mapping once provider contracts are confirmed.

### Step 8: Shortlist and write-back

Implement final progression rules, shortlist snapshots, HR System
write-back, retries, and reconciliation.

### Step 9: Pilot and hardening

Run integration/end-to-end tests, review evidence quality and fairness,
test failures and recovery, then pilot with a limited number of
requisitions.

------------------------------------------------------------------------

## 15. Technical Decisions Still Required

1.  HR System product, APIs, authentication, rate limits, pagination,
    and write-back support.
2.  Whether HR System permits proactive discovered candidates to be
    created or linked to requisitions.
3.  Fusion Mind API/webhook availability, authentication, assessment
    setup, result schema, and scoring semantics.
4.  Approved proactive discovery sources and permitted data
    retention/use.
5.  Hosting platform and organizational language/framework standards.
6.  Candidate volume, expected concurrent runs, performance targets, and
    service-level objectives.
7.  Data residency, retention, deletion, and candidate notice
    requirements.
8.  Approved criteria, mandatory gates, scoring thresholds, and
    human-review policy.
9.  Whether a durable workflow engine is needed immediately or a
    database-backed state machine is sufficient.
10. Whether a dedicated search engine or vector search is justified by
    measured needs.

------------------------------------------------------------------------

## 16. Final Architecture Summary

The proposed technical path is:

**HR System requisition → Phase 1 role brief → Phase 2 versioned
role/evaluation configuration → Phase 3A HR applicant import + Phase 3B
approved proactive discovery → unified candidate pool → evidence
extraction and deterministic evaluation → Fusion Mind Level 1 assessment
where required → validated results and updated evaluation → final
shortlist → HR System write-back.**

The most important architecture boundary is the separation between: -
AI-based interpretation and search suggestions, - deterministic
eligibility/scoring/workflow controls, - external HR System and Fusion
Mind adapters, - and the auditable final shortlist returned to the HR
System.

This design is ready for technical review, but external API details and
deployment choices should remain provisional until the relevant system
owners confirm their contracts and constraints.
