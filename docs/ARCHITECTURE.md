# Architecture — AI-Enabled Recruitment Screening System (live)

This is the **live** architecture document. It changes as decisions land in
`docs/DECISIONS.md`. The reviewed source specifications are:

| Spec | File |
|---|---|
| System design, Phases 1–4 | `docs/AI_Enabled_Recruitment_System_Design_Phases_1_to_4.md` |
| Detailed technical architecture | `docs/AI_Enabled_Recruitment_Detailed_Technical_Architecture.md` |
| Data model, Phases 1–4 | `docs/AI_Enabled_Recruitment_Data_Model_Phases_1_to_4.md` |

The specs are already plain markdown, so agents grep them directly; no PDF text extraction
(`docs/architecture_spec.txt`) is needed. If a signed-off PDF is added later, extract it to
`docs/architecture_spec.txt` and list it here. Where this file and a spec disagree, the
latest decision in `docs/DECISIONS.md` wins.

## Goal

Take an HR System requisition, build an approved role brief and versioned evaluation
configuration, pool HR applicants (3A) with proactively discovered candidates (3B), evaluate
evidence deterministically, run Fusion Mind Level 1 assessments, and write an auditable
shortlist back to the HR System — for recruiters and hiring teams.

## Stack

| Area | Choice | Status |
|---|---|---|
| Backend | Python + FastAPI, SQLAlchemy 2.0 (async), Alembic | From spec §2 |
| Database | PostgreSQL | From spec §2 |
| Background work | DB-backed state machine + queue workers (Celery/RQ + Redis); Temporal only if needed | Open (spec §15.9) |
| Object storage | S3-compatible or Azure Blob | Open (hosting) |
| Frontend | React + TypeScript on Next.js (App Router), in `frontend/`; local dev only for now | Agreed (D-20) |
| Design system | Own minimal set: Tailwind tokens + in-repo components in `frontend/src/components/ui/`; no external bundle | Agreed (D-20) |
| API types | Generated from FastAPI OpenAPI (`openapi-typescript`) | Agreed |
| Deployment | Containers on organization-approved cloud | Open (spec §15.5) |
| Sourcing helper | `Extension/` — Chrome extension exporting Sales Navigator list rows to CSV | Existing |

## Layering (backend)

Strict layered monolith: `Router → Service → Repository → Database`. No layer reaches
around the one below. External systems are adapters inside `integrations`, called from
services only. Each module has `router.py, schemas.py, models.py, service.py,
repository.py, events.py, constants.py`.

## Identity rule

One internal `candidate` may own many `candidate_source_record`s (HR applicant, discovery
source). Uncertain matches are never merged automatically (`identity_status`:
confirmed / probable / review_required / unresolved). A name alone is never a key.

## Module → tables → endpoints

Endpoints are the proposed shapes from spec §6.1, under `/api/v1`. Tables from the data
model §4.

| Module | Tables | Endpoints |
|---|---|---|
| `requisitions` | `requisition`, `requisition_snapshot`, `screening_run` | `POST /screening-runs`, `GET /screening-runs/{run_id}` |
| `role_briefs` | `role_brief_version` | `POST /screening-runs/{run_id}/approve-role-brief` |
| `role_models` | `role_configuration_version` | `POST /screening-runs/{run_id}/approve-configuration` |
| `applicants` (3A) | `candidate_source_record` (source = HR) | — (workflow step) |
| `discovery` (3B) | `discovery_query`, `discovery_batch`, `discovery_result` | — (workflow step) |
| `identity` | `candidate`, `candidate_source_record`, `candidate_profile_field` | `GET /screening-runs/{run_id}/candidates` |
| `evidence` | `candidate_evidence` | via `GET /candidates/{candidate_id}/evaluation` |
| `assessment` | `assessment_session`, `assessment_result` | `POST /webhooks/fusion-mind` |
| `evaluation` | `candidate_evaluation` | `GET /candidates/{candidate_id}/evaluation` |
| `shortlists` | `shortlist`, `shortlist_entry` | `GET /screening-runs/{run_id}/shortlist`, `POST /screening-runs/{run_id}/retry-writeback` |
| `audit` | `audit_event`, `workflow_events` | — (append-only) |
| `integrations` | `integration_attempt` | — (HR System, Fusion Mind, discovery adapters) |

## Design constraints

- Reversibility (D-02), isolation of in-progress work (D-03), fail-closed authorization
  with repository-layer row scoping (D-04).
- Business-unit/requisition scoping applies if the system serves several business units
  (spec §4.1); treat it as tenant isolation.
- AI interprets; deterministic code gates, scores and decides. Prompts/models are versioned.

## Open items (from spec §15 and data model §10)

HR System product and API; Fusion Mind contract; approved discovery sources; hosting (skipped for the MVP, D-20);
volumes/SLOs; retention and residency; workflow
engine choice.
