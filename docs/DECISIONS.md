# Architecture Decision Log

Each entry: ID, title, status, date, decision, reason. Standing rules (D-01…D-04) apply to
every feature unless a later decision names an exception and the reason for it.

---

## D-0 Project context manager

- **Status:** none installed, plan to add
- **Date:** 2026-10-22
- **Decision:** The Project Context System (PCS) is the intended durable memory for this
  project (append-only `.project-memory/events.jsonl` plus a searchable sqlite index).
- **Gap:** PCS was not available at bootstrap. It is not published on PyPI or npm, and no
  source repository or installer was supplied. `.project-memory/` is already gitignored so
  PCS can be dropped in without further changes.
- **Interim:** Checkpoints are written as markdown under `docs/checkpoints/` (committed) so
  they can be imported into PCS once it is installed.
- **Next:** Supply the PCS repo URL or package, install it next to the project, run its
  init, import `docs/checkpoints/*`, then mark this entry Accepted.

---

## D-01 Additive, never destructive

- **Status:** Accepted (standing rule)
- **Date:** 2026-10-22
- **Decision:** Close gaps by ADDING columns, tables, endpoints, pages and settings next to
  what already exists. Forward migrations are additive-only: no `DROP` (table, column,
  constraint, index) and no destructive `ALTER` in a forward migration.
- **Exceptions:** Allowed only when named in a decision entry here with the reason.

## D-02 Reversibility as a design constraint

- **Status:** Accepted (standing rule)
- **Date:** 2026-10-22
- **Decision:** Every schema change ships with a tested downgrade (upgrade → downgrade →
  upgrade round trip). Lifecycle actions (archive, withdraw, reject, expire) hide data;
  they never delete it. New behaviour ships behind a migration or a setting, so turning it
  off restores the previous behaviour exactly.

## D-03 Isolation of in-progress work

- **Status:** Accepted (standing rule)
- **Date:** 2026-10-22
- **Decision:** Every feature is built in a separate git worktree outside the running app
  folder, against a copy of the database, never against the live dev DB.

## D-04 Fail closed on authorization

- **Status:** Accepted (standing rule)
- **Date:** 2026-10-22
- **Decision:** A request with no matching permission is denied. Row scoping (by business
  unit, requisition, or tenant) runs as a repository-layer query filter derived from the
  authenticated principal. It can never be widened or bypassed by request parameters.

---

## D-05 Requisition snapshot payload storage (dev / first release)

- **Status:** Accepted — approved by the user with defaults, 2026-10-22
- **Date:** 2026-10-22
- **Feature:** Phase 1 — Requisitions (`docs/DELIVERY_PLAN.md`, BE-1.2, BE-1.5)
- **Decision:** Snapshot payloads go in a separate, restricted PostgreSQL table
  `requisition_snapshot_payload` (JSONB), behind a `SnapshotStore` interface.
  `requisition_snapshot.payload_reference` holds `db:requisition_snapshot_payload:<uuid>`.
  `payload_hash` is `sha256:<hex>` over canonical JSON (sorted keys, UTF-8, compact
  separators). It is recomputed on every read, and a mismatch raises. When a payload's
  hash equals the requisition's latest snapshot hash, that snapshot is reused. There is no
  app-level encryption in dev. Object storage and encryption plug in behind the same
  interface later.
- **Reason:** Hosting and object storage are open (Tech Arch §15.5). A DB table keeps
  writes transactional with the run, gives a simple tested downgrade, and needs no new
  infrastructure. The interface keeps the Data Model §4.2 "secure reference" option open.

## D-06 Background execution for the first release

- **Status:** Accepted — approved by the user with defaults, 2026-10-22
- **Date:** 2026-10-22
- **Feature:** Phase 1 — Requisitions (BE-1.3, BE-2.2)
- **Decision:** The DB-backed state machine is driven by an in-process `RunExecutor`
  (an asyncio task, dispatched only after the request commits). An `InlineExecutor`
  serves tests. Execution is safe against double dispatch because ingestion claims a run
  with a conditional `UPDATE … WHERE status='created'`. On startup, recovery
  re-dispatches `created` runs and blocks runs stuck in `ingesting_requisition` past a
  threshold (`ingestion_interrupted`). Each adapter call is a single attempt with no
  retries. A queue worker (Celery/RQ + Redis) and a transactional outbox are deferred
  until volumes, external waits or retries need them (Tech Arch §4.2, §15.9).
- **Reason:** It is the smallest stack that satisfies "return 202 and don't run long
  jobs in the HTTP request" (Tech Arch §4.1). The executor interface makes a later queue
  adoption additive.

## D-07 Requisition eligibility rules (rules version 1)

- **Status:** Accepted — approved by the user with defaults, 2026-10-22
- **Date:** 2026-10-22
- **Feature:** Phase 1 — Requisitions (BE-1.6, BE-1.7)
- **Decision:** A requisition is eligible when all three conditions hold:
  `source_status` is in setting `REQUISITION_ELIGIBLE_SOURCE_STATUSES` (default
  `["open"]`), `title` is non-blank, and `description` is non-blank. Other System Design
  §5 inputs (responsibilities, skills, seniority, location, employment type,
  compensation, hiring team) are optional at ingestion. Gaps in them are for the
  role_briefs stage to raise. The rules never fill defaults. Blocked-run
  `completion_reason` codes are `requisition_not_found`,
  `requisition_not_eligible_status`, `requisition_incomplete` (with
  `status_details.missing_fields`), `hr_system_unavailable`, `hr_response_invalid` and
  `ingestion_interrupted`.
- **Reason:** Title and description are the minimum needed to build a role brief
  without inventing requirements (System Design §5). The status vocabulary is the mock's
  until the real HR System contract is mapped (Data Model §2.10).

## D-08 Permission names and dev principal provider

- **Status:** Accepted — approved by the user with defaults, 2026-10-22
- **Date:** 2026-10-22
- **Feature:** Phase 1 — Requisitions (BE-0.7, BE-2.3, BE-2.4)
- **Decision:** Permissions are named `<resource>:<action>`. This feature defines
  `screening_run:create` and `screening_run:read`. The principal comes from a pluggable
  `PrincipalProvider`. The default, `AUTH_MODE=disabled`, rejects every non-public route
  with 401. `AUTH_MODE=dev_header` reads `X-Dev-Principal-Id`, `X-Dev-Permissions` and
  `X-Dev-Business-Units`, and the app refuses to start with it when
  `ENVIRONMENT=production`. No principal gets 401; a missing permission gets 403. A test
  enumerates all routes and fails on any route outside the `PUBLIC_ROUTES` allowlist
  (only `/healthz`) that has no permission dependency.
- **Reason:** D-04 requires fail closed, and production SSO is out of scope.

## D-09 Row scoping for screening runs (business unit)

- **Status:** Accepted — approved by the user with defaults, 2026-10-22
- **Date:** 2026-10-22
- **Feature:** Phase 1 — Requisitions (BE-1.3, BE-1.7, BE-2.4)
- **Decision:** `requisition` and `screening_run` carry `business_unit_key`, taken from
  the HR payload's business unit. The principal carries `business_units`. The wildcard
  `*` is honoured only when it is explicitly granted. The repository filter is: a run is
  visible when `business_unit_key ∈ principal.business_units`, or when
  `business_unit_key IS NULL AND started_by = principal.id` (a run not yet resolved, or
  blocked before resolution). A requisition outside the starter's scope is not upserted
  or snapshotted. The run is blocked with the public reason `requisition_not_found`, and
  the audit records `requisition_not_accessible`, so the API cannot be used to test
  whether a requisition exists. A run that is out of scope or missing returns 404.
- **Reason:** D-04 and Tech Arch §4.1 tenant/requisition boundaries. The business unit
  is unknown until the requisition is fetched.

## D-10 `screening_run` schema deviations from Data Model §4.3

- **Status:** Accepted — approved by the user with defaults, 2026-10-22
- **Date:** 2026-10-22
- **Feature:** Phase 1 — Requisitions (BE-1.2)
- **Decision:** These changes are additive to the spec.
  - `requisition_id` and `requisition_snapshot_id` are nullable, because a run exists in
    `created` before ingestion and a not-found run never gets them. They are guaranteed
    by the service for every status beyond `ingesting_requisition` except `blocked`.
  - New column `hr_system_key` (not null) records which HR System the run requested.
  - New column `external_requisition_id` (not null) records the requested ID, so a
    blocked run still records what was asked for.
  - New column `business_unit_key` (nullable; D-09).
  - New column `status_details` (JSONB, nullable, non-PII; for example
    `missing_fields`).

  `status` is a string validated by the application enum, with no DB CHECK constraint,
  so later states stay additive (D-01). `requisition` gains `business_unit_key`.
- **Reason:** Data Model §4.3 marks the snapshot as required, but the asynchronous 202
  flow and the "missing requisition → blocked" rule cannot meet that.

## D-11 Screening-run API contract and feature flag

- **Status:** Accepted — approved by the user with defaults, 2026-10-22
- **Date:** 2026-10-22
- **Feature:** Phase 1 — Requisitions (BE-2.3, BE-2.4, BE-2.5)
- **Decision:**
  - The POST body is `{"external_requisition_id": "<HR System ID>"}`. It is not an
    internal UUID, because the requisition may not exist internally yet. Extra fields are
    forbidden.
  - The POST returns 202 with `{run_id, status, status_url, correlation_id}` and a
    `Location` header.
  - The GET returns `run_id`, `status`, `phases`, `completion_reason`, `status_details`,
    `requisition` (a reference with snapshot ID and hash, never the raw payload),
    timestamps and `correlation_id`.
  - `phases.phase_1` is derived from the run status: `created` → `pending`;
    `ingesting_requisition` and `role_brief_draft` → `in_progress`; `blocked` →
    `blocked`.
  - Both routes are mounted only when `FEATURE_SCREENING_RUNS=true` (default `false`).
- **Reason:** Tech Arch §6.1–6.2 and D-02 ("new behaviour behind a setting").

## D-12 Audit events: append-only enforcement and actor conventions

- **Status:** Accepted — approved by the user with defaults, 2026-10-22
- **Date:** 2026-10-22
- **Feature:** Phase 1 — Requisitions (BE-0.6, BE-1.7)
- **Decision:**
  - `audit_event` is insert-only in the repository, and a DB trigger rejects UPDATE and
    DELETE.
  - `screening_run_id` is indexed but has no FK, so audit rows never cascade or block.
  - A nullable `details` JSONB column holds small non-PII facts alongside
    `details_reference`.
  - Each run status change writes its audit event in the same transaction as the change.
  - The run creation event uses actor_type `user` with the principal's ID. Workflow
    transitions use actor_type `system` with actor_id `requisitions.ingestion`. All events
    carry the run's correlation_id.
  - Event types: `ScreeningRunCreated`, `RunStatusChanged`, `RequisitionFetched`,
    `RequisitionSnapshotCaptured`.
- **Reason:** Tech Arch §8.2 and §9 Audit; Data Model §4.18. Data Model §10.9
  (immutability) is still open, and the trigger is the minimal tamper-resistant default.

## D-13 Backend layout additions to the module shape

- **Status:** Accepted — approved by the user with defaults, 2026-10-22
- **Date:** 2026-10-22
- **Feature:** Phase 1 — Requisitions (BE-0.2, BE-1.4)
- **Decision:** Cross-cutting infrastructure lives in `backend/app/core/` (`settings.py`,
  `db.py`, `security.py`, `correlation.py`, `logging.py`). It is not a domain module.
  `backend/app/modules/integrations/` may add an `adapters/<provider>/` subpackage
  (`base.py` protocol, `mock.py`, `fixtures/*.json`) next to the standard seven module
  files. Tests live in `backend/tests/`, and migrations in `backend/alembic/versions/`.
- **Reason:** The backend-engineer module shape allows no extra files without a decision
  entry. Adapters per provider are expected (Tech Arch §6.3).

---

Never renumber existing IDs. New decisions are appended as D-05, D-06, …
