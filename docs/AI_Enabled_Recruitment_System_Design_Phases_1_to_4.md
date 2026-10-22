# AI-Enabled Recruitment Screening System

## System Design Document: Phases 1--4

**Status:** Conceptual system design for review\
**Current scope endpoint:** Final shortlist returned to the external HR
System\
**Assessment provider:** Fusion Mind, third-party tool for Level 1
assessment\
**Out of scope:** Human interviews, final hiring decisions, offers,
onboarding, and post-hire learning workflows.

## 1. Executive Summary

This design covers four phases:

1.  **Job Requirement Understanding**
2.  **Role & Assessment Intelligence**
3.  **Candidate Sourcing**, with two branches:
    -   **3A Applicant-led Recruitment:** retrieve applicants from the
        external HR System.
    -   **3B Proactive Talent Discovery:** discover potential
        non-applicant candidates through approved sources.
4.  **Candidate Evidence Evaluation, Fusion Mind Level 1 Assessment, and
    Shortlisting**

The HR System is the system of record for requisitions and applicants.
The screening system retrieves the requisition and its existing
applicant list, builds a role model and assessment configuration,
combines applicant-led and proactively discovered candidates, evaluates
evidence, orchestrates Level 1 assessment through Fusion Mind, creates a
final shortlist, and writes the agreed shortlist status/data back to the
HR System.

AI supports interpretation, evidence extraction, summaries, and
search-route suggestions. Deterministic logic validates schemas, applies
approved gates and scoring, manages workflow state, enforces search
budgets, validates assessment results, and records audit events. Human
review is reserved for critical clarification, approval, and exceptions.

This is a conceptual design. The specific HR System product, its APIs,
Fusion Mind's integration contract, and the approved discovery sources
must be confirmed before implementation.

## 2. Goals and Non-Goals

### Goals

-   Ingest requisition details from the HR System.
-   Produce an approved structured role brief.
-   Create a versioned role model, criteria, scoring configuration, and
    Level 1 assessment plan.
-   Retrieve the requisition's applicants from the HR System.
-   Discover additional candidates through approved sources.
-   Normalize and deduplicate candidate records across both branches.
-   Evaluate candidate evidence against approved criteria.
-   Integrate Fusion Mind for Level 1 assessment invitations, status
    tracking, and result retrieval.
-   Incorporate validated assessment results and produce an explainable
    shortlist.
-   Return agreed shortlist records/statuses to the HR System.
-   Maintain security, privacy, fairness, provenance, and auditability.

### Non-goals

-   Interview scheduling or conducting interviews.
-   AI interview assistance.
-   Final hiring decisions, offer management, onboarding, or post-hire
    feedback.
-   Building a replacement assessment engine for Fusion Mind.
-   Scraping or bypassing source access controls or provider
    restrictions.

## 3. System Context and External Systems

### 3.1 External HR System

Expected source of: - Job requisitions and hiring requests. - Job title,
description, responsibilities, skills, level, location, and
constraints. - Applicant lists tied to a requisition. -
Candidate/application identifiers and available applicant data. -
Destination for shortlist status and agreed candidate fields.

Confirm the HR System product, APIs, authentication, pagination,
supported write-back operations, status values, and whether proactive
candidates can be created or associated with a requisition.

### 3.2 Fusion Mind

Fusion Mind is the third-party tool used for **Level 1 assessment
only**. The screening system orchestrates the integration; it does not
replace Fusion Mind's assessment engine.

Expected responsibilities, subject to provider confirmation: - Select
the configured assessment. - Create or trigger invitations. - Track
invitation and completion status. - Retrieve results. - Validate
candidate/session matching, assessment version, and result status. -
Store result references and approved score fields. - Incorporate valid
results into evaluation. - Route missing, mismatched, invalid, expired,
or anomalous results for review.

Confirm Fusion Mind APIs/webhooks, authentication, test catalogue,
result schema, score interpretation, rate limits, retry behavior, and
data-retention requirements.

### 3.3 Proactive Discovery Sources

Phase 3B must use approved source adapters and collection methods only.
Candidate sources might include authorized professional-network
integrations, licensed talent databases, organization-owned talent
pools, or other permitted sources. A source must remain disabled if its
permitted use is unclear. Do not bypass access controls, authentication,
rate limits, or provider terms.

## 4. High-Level Architecture

### 4.1 Logical components

1.  **HR System Connector:** fetches requisitions and applicants; writes
    shortlist status back.
2.  **Workflow Orchestrator:** manages phase states, retries, timeouts,
    exceptions, and run completion.
3.  **Job Requirement Understanding:** parses and structures the
    requisition and produces the role brief.
4.  **Role & Assessment Intelligence:** defines the role model,
    criteria, scoring, assessment plan, and search parameters.
5.  **Applicant-led Sourcing (3A):** imports the HR System's applicants.
6.  **Proactive Talent Discovery (3B):** runs bounded searches through
    approved source adapters.
7.  **Profile Normalization and Identity Resolution:** standardizes
    candidate records and deduplicates conservatively.
8.  **Candidate Evidence Evaluation:** extracts evidence, maps it to
    criteria, applies gates, and calculates scores.
9.  **Fusion Mind Adapter:** creates assessment invitations, tracks
    status, retrieves results, and validates them.
10. **Shortlisting Service:** applies progression rules and creates the
    final shortlist.
11. **Persistence and Audit Store:** stores versions, source records,
    evidence references, results, evaluations, events, and write-back
    status.
12. **Review Interface:** supports role/configuration approval and
    exception handling.
13. **Monitoring:** tracks connector health, processing errors, search
    budgets, assessment failures, and write-back status.

These are logical modules, not a mandate to deploy a separate
microservice for each one. A modular application with background workers
is a reasonable initial architecture.

### 4.2 Logical flow

``` text
                 ┌──────────────────────────┐
                 │ External HR System       │
                 │ Requisition + applicants │
                 └────────────┬─────────────┘
                              │ requisition
                              ▼
                 ┌──────────────────────────┐
                 │ 1. Job Requirement        │
                 │    Understanding          │
                 └────────────┬─────────────┘
                              ▼
                 ┌──────────────────────────┐
                 │ 2. Role & Assessment      │
                 │    Intelligence           │
                 └────────────┬─────────────┘
                              │ approved role model
                 ┌────────────┴─────────────┐
                 ▼                          ▼
       ┌─────────────────────┐    ┌─────────────────────┐
       │ 3A Applicant-led    │    │ 3B Proactive Talent │
       │ HR applicant list   │    │ approved sources    │
       └──────────┬──────────┘    └──────────┬──────────┘
                  └─────────────┬────────────┘
                                ▼
                 ┌──────────────────────────┐
                 │ Normalize, resolve       │
                 │ identity, deduplicate    │
                 └────────────┬─────────────┘
                              ▼
                 ┌──────────────────────────┐
                 │ 4. Candidate evidence     │
                 │ evaluation                │
                 └────────────┬─────────────┘
                              ▼
                 ┌──────────────────────────┐
                 │ Fusion Mind Level 1       │
                 │ assessment integration   │
                 └────────────┬─────────────┘
                              ▼
                 ┌──────────────────────────┐
                 │ Validate results, score, │
                 │ shortlist                │
                 └────────────┬─────────────┘
                              ▼
                 ┌──────────────────────────┐
                 │ Write shortlist/status   │
                 │ back to HR System        │
                 └──────────────────────────┘
```

## 5. Phase 1: Job Requirement Understanding

### Purpose

Convert the HR System requisition into a structured, approved role
brief.

### Inputs

-   Requisition ID and status.
-   Job title and description.
-   Responsibilities and expected outcomes.
-   Required/preferred skills, if supplied.
-   Seniority or experience level.
-   Location and work arrangement.
-   Compensation range, if available and permitted.
-   Employment type, timeline, and other constraints.
-   Hiring team information, where available.
-   Source version and timestamps.

### Process

1.  Fetch the requisition using the HR System connector.
2.  Validate that the requisition is active and eligible for screening.
3.  Extract role purpose, responsibilities, skills, seniority, outcomes,
    and constraints.
4.  Preserve original source text and source references.
5.  Identify missing critical information and ambiguities.
6.  Separate facts supplied by the HR System from AI-inferred
    suggestions.
7.  Ask for clarification only where ambiguity could materially change
    evaluation.
8.  Create a structured role brief, validate required fields, and obtain
    approval where required.

### Outputs

-   Approved role brief.
-   Structured role attributes.
-   Source requisition/version references.
-   Assumptions and unresolved questions, if any.
-   Approval and audit record.

### Completion and exceptions

Phase 1 completes when required fields are present, critical ambiguities
are resolved or explicitly accepted, and the role brief is approved. If
the requisition is closed, unavailable, or materially incomplete, stop
or hold the run rather than inventing requirements.

## 6. Phase 2: Role & Assessment Intelligence

### Purpose

Define how candidates will be evaluated. This phase does not source or
rank candidates.

### Inputs

-   Approved role brief.
-   Approved hiring policies and templates.
-   Standard skill/capability taxonomies, if available.
-   Fusion Mind assessment catalogue/configuration, once confirmed.
-   Legal, privacy, fairness, and source-use constraints.

### Process

1.  **Build role model:** responsibilities, capabilities, essential
    skills, preferred skills, transferable capabilities, and success
    outcomes.
2.  **Define criteria:** mandatory gates, preferred criteria, evidence
    types, and evidence-quality rules.
3.  **Configure scoring:** weights, rubrics, thresholds, and fit
    categories.
4.  **Design Level 1 assessment plan:** identify important gaps that a
    test can measure and map suitable Fusion Mind assessments to them.
5.  **Generate discovery parameters:** direct matches, adjacent roles,
    capability-led searches, and alternative pathways for Phase 3B.
6.  **Validate and approve:** check completeness, consistency, policy
    guardrails, and assessment availability. Version the configuration.

### Outputs

-   Structured role model.
-   Mandatory and preferred criteria.
-   Evidence standards and scoring rubrics.
-   Versioned weights and thresholds.
-   Fusion Mind Level 1 assessment plan.
-   Proactive search parameters.
-   Approved configuration and audit record.

### Governance

Mandatory gates cannot be offset by unrelated weighted scores. Missing
evidence must not automatically mean a candidate lacks the capability.
Criteria or weights must not be silently changed after candidates are
reviewed. A material change requires a new version and a documented
decision on re-evaluation.

## 7. Phase 3: Candidate Sourcing

Phase 3 has two branches with different source semantics. Both feed a
unified candidate pool.

### 7.1 Phase 3A: Applicant-led Recruitment

**Purpose:** Process people who have already applied to the requisition
and are listed in the HR System.

**Inputs** - Requisition ID. - Applicant list and application/candidate
IDs from the HR System. - Applicant profiles and resume/document
references available through the HR System. - Approved role model and
any permitted basic eligibility checks.

**Process** 1. Retrieve the applicants associated with the requisition.
2. Preserve HR System candidate and application IDs. 3. Normalize
profile fields and resume/document references. 4. Deduplicate repeated
records while retaining source provenance. 5. Validate required fields
and flag incomplete or unreadable profiles. 6. Apply only approved basic
eligibility checks intended for this step. 7. Prepare normalized
applicant records for the unified pool.

**Outputs** - Normalized applicant records linked to HR System IDs. -
Data-quality and eligibility flags. - Duplicate-resolution records. -
Source provenance. - Applicants ready for Phase 4.

**Boundary:** Phase 3A does not discover new people. It retrieves
existing applicants from the HR System.

### 7.2 Phase 3B: Proactive Talent Discovery

**Purpose:** Find potentially suitable non-applicant candidates through
approved sources.

**Inputs** - Approved role model and search parameters. - Authorized
source adapters. - Candidate target, initial budget, expansion budget,
hard maximum, and stopping rules. - Privacy and data-use constraints.

**Process** 1. Generate a portfolio of search routes: direct title/skill
matches, adjacent roles, capability-led searches, transferable skills,
and alternative career paths. 2. Execute searches through approved
connectors in bounded batches. 3. Normalize profiles and preserve
source, query/route, collection time, and source reference. 4.
Deduplicate within discovery results and against the applicant pool
where permitted. 5. Measure relevance yield, route diversity, evidence
strength, unique candidate yield, and marginal discovery value. 6. Adapt
routes or expand the budget only when justified and within a hard
maximum. 7. Stop when the approved target is met, diminishing returns
meet the configured rule, the budget is exhausted, or source/policy
limits require stopping. 8. Mark whether the target was met or discovery
ended with limited results.

**Outputs** - Discovered candidate records. - Search coverage and yield
metrics. - Source/query provenance. - Deduplication outcomes. - Budget
consumed and stopping reason. - Candidates ready for the unified pool.

**Boundary:** Do not lower suitability thresholds to hit a candidate
target. Use only permitted sources and methods.

### 7.3 Unified candidate pool and identity resolution

-   Preserve original source records and identifiers.
-   Track whether each candidate came from 3A, 3B, or both.
-   Prefer reliable identifiers for deterministic deduplication.
-   Treat uncertain fuzzy matches as review cases rather than definite
    duplicates.
-   Keep field-level provenance and avoid silently overwriting HR System
    data with external data.
-   Respect source-specific retention and deletion requirements.

Suggested candidate states: `imported`, `normalized`,
`duplicate_review`, `ready_for_evaluation`, `held_for_data_quality`,
`excluded_by_approved_gate`.

## 8. Phase 4: Candidate Evidence Evaluation, Fusion Mind Assessment, and Shortlisting

### Purpose

Evaluate the unified pool, run Level 1 assessments through Fusion Mind
where required, incorporate validated results, create a final shortlist,
and return the agreed result to the HR System.

### Inputs

-   Unified candidate pool.
-   Approved role model and configuration version.
-   Resumes, profiles, work history, projects, qualifications,
    certifications, and other permitted evidence.
-   Fusion Mind assessment plan.
-   Internal and external candidate/requisition identifiers.

### Process

1.  Extract and structure candidate evidence.
2.  Map evidence to approved role criteria.
3.  Apply mandatory gates and calculate an initial profile-evidence
    evaluation.
4.  Decide which candidates require Level 1 assessment under the
    approved plan.
5.  Trigger Fusion Mind assessment invitations through its supported
    integration.
6.  Track invitation and completion status.
7.  Retrieve and validate results and candidate/session mapping.
8.  Incorporate valid results using the approved scoring configuration.
9.  Recalculate the evaluation, preserving the profile and assessment
    contributions separately.
10. Create a ranked or categorized shortlist with evidence-linked
    rationale and uncertainty flags.
11. Write shortlist status and agreed fields back to the HR System.

### 8.1 Evidence handling

AI may extract skills, responsibilities, projects, outcomes,
qualifications, and relevant evidence; map evidence to criteria; and
summarize strengths, gaps, contradictions, and uncertainty. Material
claims should retain a source reference and, where possible, a location
in the source document.

Distinguish: - Evidence quality from model confidence. - Missing
information from negative evidence. - Profile-evidence evaluation from
assessment results.

### 8.2 Scoring and progression

-   Use the approved configuration version.
-   Mandatory gates remain separate from weighted scores.
-   Missing or unclear evidence should be marked unknown or needs review
    where appropriate.
-   Scores must be explainable through criterion-level breakdowns.
-   Thresholds and weights must be calibrated before production use;
    illustrative values are not production defaults.
-   The target number of shortlisted candidates must not cause
    suitability criteria to be lowered.

### 8.3 Fusion Mind Level 1 integration

Expected flow, subject to provider capability: 1. Select candidates
requiring assessment. 2. Create an invitation/session. 3. Store the
provider session ID and internal candidate mapping. 4. Track invitation
and completion state. 5. Receive a webhook or poll status if supported.
6. Fetch the result. 7. Validate candidate/session, requisition,
assessment version, and result finality. 8. Store result reference and
approved score fields. 9. Incorporate valid results into evaluation. 10.
Record each integration event.

Suggested internal assessment states: `not_required`,
`pending_invitation`, `invited`, `in_progress`, `completed`,
`result_received`, `validated`, `invalid_result`,
`candidate_mapping_error`, `provider_error`, `expired`, `manual_review`.

Map Fusion Mind's actual statuses to these only after reviewing its
integration contract.

**Failure handling** - Retry transient provider errors with bounded
backoff. - Use idempotency controls to avoid duplicate invitations or
result processing. - Never convert a missing result to a zero score. -
Never fail a candidate solely because of a provider outage or
integration error. - Route mismatched, invalid, or anomalous results to
review. - Keep assessment results distinguishable from profile scores.

### 8.4 Shortlist outputs and HR System write-back

Outputs: - Final shortlist. - Candidate-level evaluation report and
criterion breakdown. - Validated Fusion Mind result references/scores. -
Strengths, gaps, and uncertainty flags. - Review and exception
outcomes. - Shortlist run summary and write-back status.

Confirm the HR System's supported fields. Potential fields include
requisition ID, candidate/application ID, screening run ID, shortlist
status, timestamp, approved reason code or summary, assessment status if
permitted, and a report reference if supported.

For proactively discovered candidates, confirm whether the HR System
allows creating candidate records or associating non-applicants with a
requisition. Do not assume they can be written back through the same
endpoint as applicants.

Distinguish `shortlist_ready` from `writeback_succeeded`. Use idempotent
writes, logging, retries, and reconciliation.

Suggested outcome categories (to map to actual HR System values): -
`shortlist` - `needs_review` - `not_shortlisted` -
`assessment_pending` - `assessment_exception`

## 9. Conceptual Data Model

The exact schema depends on the external contracts.

### Requisition

-   Internal requisition ID, HR requisition ID, source version, status,
    timestamps.

### RoleBrief

-   Role brief ID, requisition ID, version, structured fields, source
    references, assumptions, approval state, approver, timestamp.

### RoleEvaluationConfiguration

-   Configuration ID, role brief ID, version, mandatory criteria,
    preferred criteria, weights, thresholds, evidence rules, assessment
    plan, search parameters, approval state.

### Candidate

-   Internal candidate ID, identity-resolution state, timestamps.

### CandidateSourceRecord

-   Source record ID, internal candidate ID, source type
    (`hr_applicant`, `proactive_discovery`), external
    candidate/application ID, source reference, collection time, payload
    reference.

### CandidateEvidence

-   Evidence ID, candidate ID, source record ID, evidence type, mapped
    criterion, summary, source location, observation time, quality
    indicator, uncertainty indicator.

### AssessmentSession

-   Internal session ID, candidate ID, requisition ID, provider,
    provider session ID, configuration version, state,
    invitation/completion timestamps.

### AssessmentResult

-   Result ID, session ID, provider result ID/version, status, score
    payload reference, validation time, notes.

### CandidateEvaluation

-   Evaluation ID, candidate ID, requisition ID, configuration version,
    profile score, assessment score if applicable, gate results,
    criterion breakdown, uncertainty flags, recommendation, timestamp.

### Shortlist

-   Shortlist ID, requisition ID, evaluation run ID, configuration
    version, candidate IDs, creation time, write-back state.

### Workflow/Audit Event

-   Event ID, entity type/ID, event type, actor, timestamp, correlation
    ID, details reference.

### Data principles

-   Keep raw source references separate from normalized data.
-   Preserve provenance and timestamps.
-   Version configurations and evaluation runs.
-   Minimize copies of personal data.
-   Apply field-level access and retention policies.
-   Do not use candidate data for unrelated model training without a
    separately approved basis.

## 10. Workflow State Management

Suggested run states: `created`, `ingesting_requisition`,
`role_brief_draft`, `awaiting_role_approval`, `role_configuration`,
`awaiting_configuration_approval`, `sourcing`, `candidate_pool_ready`,
`evaluating_profiles`, `assessment_processing`, `shortlist_ready`,
`writing_back_to_hr`, `completed`, `completed_with_exceptions`,
`blocked`, `cancelled`.

Rules: - Pin requisition and configuration versions for each run. -
Retries must not duplicate records, invitations, evaluations, or
writes. - Manual review is an explicit state. - Failure of Phase 3B need
not block Phase 3A unless business policy requires both. - Fusion Mind
outages should hold or exception-route candidates who require
assessment, not silently fail them. - Preserve partial progress and
clearly label incomplete runs.

## 11. Integration Boundaries

These are illustrative logical operations, not confirmed API contracts.

### HR System connector

-   Retrieve requisition.
-   Retrieve applicants for a requisition.
-   Retrieve candidate details/documents where supported.
-   Write shortlist/status to the agreed resource.

### Internal screening API

-   Create and inspect screening runs.
-   Retrieve candidates and evaluations.
-   Approve role brief and evaluation configuration.
-   Retrieve shortlist.
-   Retry failed write-back.

### Fusion Mind adapter

-   Create/invite assessment.
-   Query assessment status.
-   Receive completion event if supported.
-   Retrieve result.
-   Validate session and candidate references.

Integration standards: - Use provider-approved authentication, TLS,
secret storage, schema validation, correlation IDs, idempotency, bounded
retries, and durable exception handling. - Keep provider-specific
payloads behind adapters. - Do not invent API paths until official
documentation is available.

## 12. AI Versus Deterministic Responsibilities

  -----------------------------------------------------------------------
  Area                    AI-assisted work        Deterministic controls
  ----------------------- ----------------------- -----------------------
  Phase 1                 Interpret role text,    Validate fields,
                          extract concepts,       preserve source,
                          identify ambiguity      enforce approval

  Phase 2                 Suggest capabilities,   Apply policy
                          criteria wording,       guardrails, validate
                          evidence mappings,      configuration, version
                          assessment choices      and freeze rules

  Phase 3A                Parse resume/profile    Retrieve HR applicants,
                          content if needed       preserve IDs, validate
                                                  and deduplicate

  Phase 3B                Generate/refine search  Source allowlist,
                          routes and interpret    budget, stopping rules,
                          relevance               audit, deduplication

  Phase 4                 Extract/summarize       Apply gates, calculate
                          evidence, map evidence  configured scores,
                          to criteria, explain    validate results,
                          gaps                    create shortlist, write
                                                  back
  -----------------------------------------------------------------------

AI must not silently modify approved criteria or make unlogged changes
to external-system state.

## 13. Security, Privacy, Fairness, and Audit

### Security

-   Least-privilege connector credentials.
-   Encryption in transit and at rest.
-   Separate development/test/production credentials.
-   Role-based access to candidate data.
-   Audit access and configuration changes.
-   Treat candidate documents and profile text as untrusted data;
    prevent prompt injection from changing system behavior.

### Privacy and source use

-   Collect only data required for the hiring purpose.
-   Record source and collection time for external data.
-   Define retention, deletion, and candidate notice with
    HR/privacy/legal owners.
-   Respect provider terms and data-use restrictions.
-   Do not infer or score sensitive personal attributes.

### Fairness and explainability

-   Evaluate job-related evidence, not keyword similarity alone.
-   Missing online information is not proof of inability.
-   Apply the same approved criteria/configuration version consistently.
-   Ensure mandatory gates are explicit, job-related, and approved.
-   Provide evidence-linked explanations and a review path.
-   Do not treat historic human decisions as unquestionable ground
    truth.

### Audit

Record requisition and configuration versions, search routes/sources,
evidence references, assessment events, scoring/gate outcomes, manual
overrides and reasons, shortlist creation, and HR write-back results.

## 14. Non-Functional Requirements

These need measurable targets agreed with stakeholders.

-   **Reliability:** bounded retries, idempotent operations, durable
    workflow state, recoverable partial progress.
-   **Scale:** paginated applicant ingestion, asynchronous batch
    processing, bounded search and assessment concurrency.
-   **Observability:** phase duration, connector errors, parsing
    failures, duplicate rates, assessment-result failures, search
    yield/budget, and write-back failures.
-   **Maintainability:** modular adapters, versioned schemas, scoring
    logic separate from prompts, testable core evaluation.
-   **Recovery:** agreed backup, restore, recovery-time, and
    recovery-point objectives.

## 15. Testing and Validation

### Unit tests

-   Role schema validation.
-   Mandatory gates and scoring.
-   Search budgets and stopping.
-   Identity resolution/deduplication.
-   Fusion Mind status mapping.
-   HR write-back mapping.

### Integration tests

-   Requisition retrieval and applicant pagination.
-   HR status write-back and retries.
-   Fusion Mind invitation, status, result retrieval, and validation in
    a sandbox.
-   Source authorization and connector failure handling.

### End-to-end scenarios

-   Complete and incomplete requisitions.
-   Applicant-only, discovery-only, and combined sourcing.
-   Overlapping candidate identities.
-   Missing candidate evidence.
-   Pending assessment.
-   Provider outage, malformed result, or candidate/result mismatch.
-   HR write-back failure after shortlist creation.
-   Requisition changes during a screening run.

### Quality evaluation

-   Hiring-expert review of role briefs.
-   Evaluation of evidence extraction and criterion mapping.
-   Scoring calibration and consistency checks.
-   Search relevance, diversity, and duplicate metrics.
-   Assessment result mapping verification.
-   Human review of shortlist quality.
-   Fairness and error-pattern monitoring before broad rollout.

## 16. Deployment Approach

Start with a modular application, not necessarily microservices: -
Web/API and review interface. - Background worker for document
processing, discovery, and assessment orchestration. - Workflow queue or
durable workflow engine. - Relational database for structured records. -
Secure object/document storage where needed. - Audit/event storage. -
Secrets management and monitoring.

Use development with synthetic/anonymized data, integration testing with
HR System and Fusion Mind sandbox access, and production only after
source approval, security, retention, and operational ownership are
defined. Select technology stack after confirming enterprise standards,
volume, hosting, and integration constraints.

## 17. Open Decisions

### HR System

-   Product and API availability.
-   Requisition/applicant pagination and filtering.
-   Supported shortlist write-back endpoint and status values.
-   How proactively discovered non-applicants can be represented.
-   Permitted data fields and report references.

### Fusion Mind

-   API/webhook capability and authentication.
-   Test catalogue and assessment configuration.
-   Invitation and result retrieval mechanism.
-   Score interpretation and version metadata.
-   Rate limits, retries, retention, and security.

### Proactive discovery

-   Approved sources and permitted collection methods.
-   Initial/expansion/hard search budgets.
-   Candidate target and diminishing-return rule.
-   Retention and use restrictions.

### Evaluation and operations

-   Role/configuration approvers.
-   Approved mandatory gates, weights, and thresholds.
-   Human review policy.
-   Candidate notice and retention policy.
-   Expected volume, performance targets, hosting/data residency, and
    operational ownership.

## 18. Recommended Delivery Sequence

1.  **Integration discovery:** confirm HR System and Fusion Mind
    contracts, approved sources, schemas, security, and status mappings.
2.  **Phases 1--2:** requisition ingestion, role brief, approval,
    versioned role model, criteria, scoring, assessment plan.
3.  **Phase 3A:** applicant retrieval, normalization, IDs, and
    deduplication.
4.  **Phase 3B:** approved source adapters, search routes, bounded
    search, metrics, budgets, stopping rules.
5.  **Phase 4 profile evaluation:** evidence extraction, criteria
    mapping, gates, scoring, uncertainty, and reporting.
6.  **Fusion Mind integration:** invitations, status tracking, result
    retrieval, validation, score mapping.
7.  **Shortlist and HR write-back:** progression rules, idempotent
    writes, retries, reconciliation.
8.  **Controlled pilot:** end-to-end, quality, security, privacy, and
    fairness validation before scale-up.

## 19. Scope Summary

The current scope begins with a requisition in the external HR System
and ends when the screening solution creates a final shortlist and
returns the agreed shortlist data/status to that system.

**HR System requisition → Phase 1 role brief → Phase 2 approved
evaluation/assessment configuration → Phase 3A HR applicants + Phase 3B
proactive discovery → unified candidate pool → Phase 4 evidence
evaluation + Fusion Mind Level 1 assessment → final shortlist → HR
System write-back.**

Fusion Mind remains a third-party Level 1 assessment provider. The
screening system orchestrates the integration and uses validated results
in evaluation. Human interviews and subsequent hiring stages remain
future planning and are outside this document's current scope.
