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

## D-14 Interactive docs and OpenAPI route are not mounted

- **Status:** Accepted — approved by the user, 2026-10-22
- **Date:** 2026-10-22
- **Feature:** Phase 1 — Requisitions (BE-0.2, BE-0.7; Phase 0 deviation a)
- **Decision:** `create_app` sets `docs_url`, `redoc_url` and `openapi_url` to `None`, so
  `/healthz` stays the only public route (D-08 `PUBLIC_ROUTES`). Code can still read the
  schema through `app.openapi()`. If someone later wants served docs, they get a separate
  decision with two options: mount them behind `require_permission("api_docs:read")`, or
  only when `ENVIRONMENT` is not `production`. Any such route still has to pass the
  route audit.
- **Reason:** FastAPI's default `/docs`, `/redoc` and `/openapi.json` would be public
  routes outside the allowlist. The startup route check (D-15) would reject them anyway.
  Nothing in this feature needs served docs, and TypeScript type generation is deferred
  (Phase 2 deferred list).
- **Consequence:** Developers cannot browse `/docs` locally. A later export script writes
  `app.openapi()` to a file (Phase 0 deferred list).

## D-15 Audit and startup hardening beyond D-08 and D-12

- **Status:** Accepted — approved by the user, 2026-10-22
- **Date:** 2026-10-22
- **Feature:** Phase 1 — Requisitions (BE-0.6, BE-0.7; Phase 0 deviation c)
- **Decision:** This extends D-12 and D-08. It does not rewrite them. The following,
  already built in Phase 0, stay in place:
  - A statement-level trigger on `audit_event` rejects TRUNCATE, in addition to the D-12
    UPDATE and DELETE trigger. `downgrade()` drops both triggers.
  - `create_app` refuses to start if any route outside `PUBLIC_ROUTES` lacks a
    `require_permission` dependency. D-08 required only a test.
  - `AuditService.record` raises `MissingCorrelationIdError` unless a correlation ID is
    passed or set in the context.
  - `details` holds at most 32 keys, and every key and string value is at most 256
    characters.
- **Reason:** These are all fail-closed additions in the spirit of D-04 and D-12.
  TRUNCATE skips row triggers, so without its own trigger the append-only guarantee had a
  hole. The details limits keep free text, which could be PII, out of audit rows.
- **Consequence:** Work that runs outside a request, such as BE-2.2 startup recovery and
  executor tasks, must pass the run's `correlation_id` explicitly (D-12 already requires
  this). Test cleanup cannot TRUNCATE `audit_event`. It relies on rolled-back transactions
  or on `downgrade base`.

## D-16 Alembic CLI refuses non-copy databases in development and test

- **Status:** Accepted — approved by the user, 2026-10-22
- **Date:** 2026-10-22
- **Feature:** Phase 1 — Requisitions (BE-1.8; Phase 0 deviation d)
- **Decision:** `alembic/env.py` applies the D-03 copy rule (database name ends in `_copy`
  or `_test`) before it connects, whenever `ENVIRONMENT` is `development` or `test`.
  Staging and production migrations are not affected. The guard moves to
  `app/core/db_guard.py`, which adds a file to the D-13 `core/` list, and
  `tests/db_guard.py` stays as a re-export.
- **Reason:** Today only pytest is guarded. A manual `alembic downgrade base` with a wrong
  `backend/.env` would destroy a non-copy database, including audit rows that are meant
  to be permanent. D-03 says in-progress work never touches anything but a copy.
- **Alternative:** Leave it as is and rely on `backend/.env` discipline, which has no code
  change but also no protection.

## D-17 Backend dependency locking

- **Status:** Accepted — approved by the user, 2026-10-22
- **Date:** 2026-10-22
- **Feature:** Phase 1 — Requisitions (Phase 0 deviation f)
- **Decision:** Keep the compatible ranges in `backend/pyproject.toml`, and commit a
  lockfile generated from them for reproducible installs into `backend/.venv`. The
  default tool is `pip-compile` (pip-tools), producing `backend/requirements.lock` and
  `backend/requirements-dev.lock`. The alternative is `uv lock`. Keep the floor
  `fastapi>=0.159`, which `fastapi.routing.iter_route_contexts` (the route audit) needs.
- **Reason:** Ranges alone let two installs of the same commit resolve different
  versions. Because security code depends on a recent FastAPI API, an unnoticed upgrade or
  downgrade could break the route audit. Generating the lock adds files only, and
  deleting the lock reverts it.

## D-18 MVP mode: light testing

- **Status:** Accepted — user instruction, 2026-10-22
- **Date:** 2026-10-22
- **Feature:** Phase 1 — Requisitions (Phase 2 onward; applied retroactively to Phase 1 ticking)
- **Decision:** The project is in MVP mode ("no need to lot of testing").
  - Tests are limited to the ones named in Done-when lines: one focused test per
    behaviour. Do not add exhaustive matrices, parametrized permutations or extra
    hardening tests beyond what a Done-when names.
  - Still mandatory for every phase: `ruff check`, `mypy app`, `pytest`, and the migration
    round trip (`upgrade head → downgrade -1 → upgrade head`). They are cheap and they
    enforce D-02.
  - Ticking: the architect checks that each Done-when test exists under its exact name in
    the named file and that the orchestrator's run shows it passing. Assertions are not
    audited line by line.
  - Standing rules D-01…D-04 are unchanged. Only the depth of verification changes.
- **Reason:** User instruction. The cost of verification should match an MVP.
- **Revisit:** before any pilot or production use. At that point, restore the trimmed
  tests listed in the Phase 2 deferred list and re-audit assertions for security-relevant
  tests (scoping, permissions, audit).

## D-19 Run scope capture and business-unit rules (amends D-09, D-10)

- **Status:** Accepted — approved by the user, 2026-10-22
- **Date:** 2026-10-22
- **Feature:** Phase 1 — Requisitions (BE-1.2, BE-1.3, BE-1.7; engineer deviation found
  during Phase 1 verification)
- **Decision:** This amends D-09 and D-10 additively. It does not rewrite them.
  - **New column (amends D-10):** `screening_run.scope_business_units`, `varchar[] NOT NULL
    DEFAULT '{}'`, added in migration `0002_requisitions` and dropped by its downgrade.
    `ScreeningRunService.create` fills it from the authenticated principal's
    `business_units` at run creation. It is never taken from request input (D-04).
  - **Ingestion scope (amends D-09):** ingestion runs without a live principal (in-process
    or recovered runs), so the D-09 starter-scope check compares the HR payload's
    `business_unit` against the run's captured `scope_business_units`. Scope is fixed when
    the run is created. If a principal's units are revoked later, in-flight runs that
    principal started are not affected.
  - **Wildcard (clarifies D-09):** a principal granted `*` sees every run that has a
    non-null `business_unit_key`. Unresolved runs (`business_unit_key IS NULL`) are still
    visible only to their starter. At ingestion, a captured `*` accepts any business unit.
  - **Payload business unit is required (clarifies D-07/D-09):** the HR payload must carry
    `business_unit`. If it is missing, or if it is the literal `*`, the run is blocked with
    `hr_response_invalid`. A source record can therefore never claim wildcard scope.
- **Reason:** Without a captured scope, background ingestion has no principal to check
  against. It would then either skip the D-09 check (failing open) or need the request
  principal to outlive the request. Capturing the scope at creation keeps the check fail
  closed and derived from the principal.
- **Consequence:** Q-2 (which HR field carries the business unit, and whether there is
  more than one BU) stays open in practice. The mock assumes `business_unit`. Until Q-2 is
  answered, a real HR System without that field would block every run as
  `hr_response_invalid`.
- **Alternatives:** (a) Re-resolve the starter's current scope from the principal store at
  ingestion time. That reflects revocations but needs a principal lookup with no request,
  and there is none today. (b) Treat a missing `business_unit` as unscoped (NULL), which
  fails open and is rejected under D-04.
- **Reversibility:** the column is additive and is covered by the `0002` round trip.
  Rejecting this decision means a follow-up task to change the scope source. The column
  can stay unused (D-01).

---

Never renumber existing IDs. New decisions are appended as D-05, D-06, …
