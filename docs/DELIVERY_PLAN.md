# Delivery Plan — phases + tasks

---

## Feature: Phase 1 — Requisitions (requisition ingestion and screening run)

- **Kickoff:** `docs/prompts/kickoffs/2026-10-22-phase1-requisitions.md`
- **Plan status:** APPROVED by the user, 2026-10-22 — all defaults accepted (Q-1…Q-9 below), D-05…D-13 Accepted. Build one phase at a time.
- **Plan author:** solution-architect, 2026-10-22
- **Specs used:** System Design §5; Technical Architecture §2, §4.1–4.3, §5.1, §6.1–6.3,
  §8, §9, §14 Steps 2–3; Data Model §2, §4.1–4.3, §4.17–4.18, §6, §7.1, §8.
- **Starting point:** No `backend/` or `frontend/` exists yet. `scripts/start-backend.sh`
  expects `backend/.venv` and `uvicorn app.main:app`. `Extension/` is unrelated and is not
  touched.
- **Frontend:** No FE tasks in this feature. The kickoff defaults to none, and nothing in
  the acceptance criteria needs a page.
- **PROPOSED defaults:** Items marked **PROPOSED (D-nn)** rely on decisions D-05…D-13 in
  `docs/DECISIONS.md`. Those decisions are "Proposed — awaiting approval". I chose the
  defaults so the plan can be built. If approval changes a default, I amend the tasks it
  affects before the build starts.

### Standing-rule compliance (applies to every task below)

- **D-01:** Forward migrations only add tables, columns, indexes, constraints and
  triggers. Drops happen only in `downgrade()`.
- **D-02:** Each migration task has its own downgrade and a round-trip test. New
  behaviour is behind settings that default to off: `FEATURE_SCREENING_RUNS=false`,
  `AUTH_MODE=disabled`. Runs are never deleted. `blocked` is a status, not a deletion.
- **D-03:** Each phase starts with its own worktree task, outside `/home/user/HR_phase1`,
  against a database copy. The test harness refuses any database that is not a copy.
- **D-04:** Each endpoint task names its permission. With no principal the request gets
  401. With no permission it gets 403. Row scoping is a repository filter built from the
  principal (D-09).

### Status flow implemented by this feature (Data Model §7.1 subset)

```
created ──claim──▶ ingesting_requisition ──eligible──▶ role_brief_draft   (stops here; role_briefs is the next feature)
                           │
                           └──not found / not accessible / closed / incomplete / adapter failure / invalid response──▶ blocked (+ completion_reason)
```

---

### Phase 0 — Minimal backend foundation

Goal: a runnable FastAPI app with settings, async DB access, Alembic, a test harness that
only accepts a DB copy, correlation IDs, the `audit_event` table, and a fail-closed
principal/permission dependency. It contains no requisition logic.

- [x] BE-0.1 Isolation setup (D-03). Create git worktree
  `/home/user/HR_phase1-worktrees/p1req-phase0` on branch `feature/p1-requisitions-phase0`.
  Create an empty PostgreSQL database `hr_phase1_p1req_copy` for this phase. No live dev DB
  exists yet, so the "copy" is a dedicated new database, never a shared one. Record both
  in the engineer's report.
  Done-when: the report shows `git worktree list` output with the new path, and `psql -l`
  lists `hr_phase1_p1req_copy`.
- [x] BE-0.2 App skeleton and settings. Add `backend/pyproject.toml` (Python 3.12, FastAPI,
  SQLAlchemy 2 async + asyncpg, Alembic, pydantic-settings, pytest, pytest-asyncio, httpx,
  ruff, mypy). Add `backend/app/main.py` (app factory) and `backend/app/core/settings.py`
  with `ENVIRONMENT`, `DATABASE_URL`, `AUTH_MODE` (default `disabled`),
  `FEATURE_SCREENING_RUNS` (default `false`) and `HR_SYSTEM_ADAPTER` (default unset).
  Startup validation fails closed: if `ENVIRONMENT=production` and `AUTH_MODE=dev_header`
  or `HR_SYSTEM_ADAPTER=mock`, the app refuses to start. Add `GET /healthz`. It is the only
  public route and sits in an explicit `PUBLIC_ROUTES` allowlist. Layout follows
  **PROPOSED (D-13)**.
  Done-when: `test_settings.py::test_production_rejects_dev_auth_and_mock_adapter` passes, and `GET /healthz` returns 200 in `test_health.py::test_healthz_ok`.
- [x] BE-0.3 Async DB and Alembic. Add `backend/app/core/db.py` (async engine, session
  dependency, one transaction per unit of work) and `backend/alembic/` with an async
  `env.py` that reads `DATABASE_URL` from settings. Add no tables yet.
  Done-when: `alembic current` against `hr_phase1_p1req_copy` runs without error (output in the report).
- [x] BE-0.4 Test harness and DB-copy guard. Add `backend/tests/conftest.py`. It refuses
  to run unless the database name in `DATABASE_URL` ends in `_copy` or `_test`. It
  migrates to head once per session, isolates each test in a rolled-back transaction, and
  provides an httpx `AsyncClient`. Add
  `tests/migrations/test_round_trip.py::test_migration_round_trip`, which runs
  `upgrade head → downgrade base → upgrade head` on the copy. Every later migration task
  relies on this test.
  Done-when: `test_db_guard.py::test_refuses_non_copy_database` and `test_round_trip.py::test_migration_round_trip` pass.
- [x] BE-0.5 Correlation ID and safe logging. Middleware accepts `X-Correlation-ID` if it
  is a UUID or `[A-Za-z0-9-]{1,64}`, otherwise it generates a UUID4. The ID is stored in a
  contextvar, echoed in the response header, and included in structured JSON logs. A log
  filter keeps request and response bodies out of logs (Tech Arch §6.2, §9).
  Done-when: `test_correlation.py::test_echoes_valid_and_replaces_invalid_correlation_id` passes.
- [x] BE-0.6 `audit` module and the `audit_event` table. Migration `0001_audit_event`
  creates the Data Model §4.18 columns plus a `details` JSONB field (nullable,
  non-PII). It adds the index `audit_event(screening_run_id, timestamp)` and a trigger
  that rejects UPDATE and DELETE (**PROPOSED (D-12)**). `screening_run_id` has no FK, by
  design (D-12). The repository is insert-only, and `AuditService.record(...)` joins the
  caller's transaction. `downgrade()` drops the trigger, the function and the table.
  Done-when: `test_audit.py::test_audit_event_is_append_only` (UPDATE and DELETE raise) and `test_migration_round_trip` pass.
- [x] BE-0.7 Principal and permission dependency. Add `backend/app/core/security.py`: a
  `Principal` (id, permissions, business_units), a `PrincipalProvider` interface, a
  `DisabledPrincipalProvider` (the default, which always returns 401), a
  `DevHeaderPrincipalProvider` used only when `AUTH_MODE=dev_header`, and
  `require_permission(name)`. With no principal the request gets 401. Without the
  permission it gets 403 (**PROPOSED (D-08)**). A route-audit test enumerates every route
  and fails when a route outside `PUBLIC_ROUTES` lacks a `require_permission` dependency.
  Done-when: `test_security.py::test_no_principal_401_missing_permission_403` and `test_security.py::test_every_route_declares_permission` pass.

- [x] **Phase 0 Done-when:** in the Phase 0 worktree against `hr_phase1_p1req_copy`, the
engineer reports real output with every check passing: `ruff check`, `mypy app`,
`pytest`, and `alembic upgrade head && alembic downgrade -1 && alembic upgrade head`.

**Verified 2026-10-22 (solution-architect).** Code read in `backend/` (fast-forwarded from
`feature/p1-requisitions-phase0`, worktree `/home/user/HR_phase1-worktrees/p1req-phase0`
at `b139e4e`). Every Done-when test exists under its exact name and asserts the stated
behaviour, not a trivial pass. Orchestrator output from the worktree against
`hr_phase1_p1req_copy`:
- `ruff check .`: All checks passed. `mypy app`: no issues in 17 source files.
- `pytest -q`: 26 passed. The 8 Done-when node IDs gave 15 passed, because
  `test_refuses_non_copy_database` is parametrized 8 ways.
- `alembic upgrade head; alembic downgrade base; alembic upgrade head; alembic current`
  ended at `0001_audit_event (head)`. With a single revision, `downgrade base` is the same
  as `downgrade -1`.
- `git worktree list` shows the Phase 0 path. `psql -l` lists `hr_phase1_p1req_copy`.
- No forward-migration drops, no deletions vs the base commit, no `.env` tracked (the root
  `.gitignore` ignores `.env` and `.env.*`).
- Engineer deviations a–f are logged as D-14…D-17 (Accepted 2026-10-22). Follow-ups are BE-1.8,
  BE-2.6 and the deferred items below.

**Reversibility:** everything is new under `backend/`. To roll back, run `alembic
downgrade base` on the copy and remove the worktree or revert the branch. Afterwards
`audit_event` is gone and no other state remains. Once real audit data exists in a shared
environment, downgrading `0001` is not allowed without a new decision, because it would
destroy audit records.

**Deferred from Phase 0:** production SSO/OIDC provider (out of scope; the
`PrincipalProvider` interface is the seam), `workflow_events` table (not needed;
`audit_event` covers state transitions), secrets manager, metrics/tracing exporters, rate
limiting and request-size limits (Tech Arch §6.2; no external exposure yet), CI pipeline
definition.

Also deferred from Phase 0 after verification (2026-10-22):
- **Nullable `audit_event.screening_run_id`** for audit events that are not about a run
  (admin, configuration). It is NOT NULL today, which matches Data Model §4.18 and every
  event in this feature. Relaxing it belongs to the first feature that writes non-run
  events, and that feature needs its own decision first. Its downgrade cannot restore NOT
  NULL once null rows exist, and append-only rows cannot be deleted to make that possible.
- [x] **Dependency lockfile** (D-17, Accepted). There is no lockfile today, and versions are
  ranges in `backend/pyproject.toml`. If D-17 is accepted, generate and commit the lock
  before the Phase 1 build starts.
  **Done** in commits `967fba0` / `add315f`: `backend/requirements.lock` and
  `backend/requirements-dev.lock` are committed (verified 2026-10-22).
- **Committed OpenAPI export** (D-14, Accepted). The docs and OpenAPI routes are not
  mounted. An export script that writes `app.openapi()` to a file comes with the first
  frontend feature, which matches the Phase 2 deferral of TypeScript type generation.
- [x] **Tests for the 32-key `details` limit and the startup route check.** Today
  `test_details_must_be_small` covers only string length. Add these with D-15 if it is
  accepted.
  **Done** in commits `967fba0` / `add315f`:
  `test_audit.py::test_details_key_count_and_key_length_limits` and
  `test_security.py::test_create_app_refuses_unprotected_route` exist and pass in the
  orchestrator's 59-passed run (verified 2026-10-22).

---

### Phase 1 — Requisition data, HR System mock adapter, snapshot and ingestion service (no HTTP)

Goal: the full ingestion workflow, callable as a service. Phase 1 exposes no new
endpoint, which keeps it inert in a running app.

- [x] BE-1.1 Isolation setup (D-03). Create worktree
  `/home/user/HR_phase1-worktrees/p1req-phase1` on branch `feature/p1-requisitions-phase1`,
  based on the reviewed Phase 0 branch. Reuse `hr_phase1_p1req_copy` migrated to Phase 0
  head, or recreate it.
  Done-when: the report shows `git worktree list` with the Phase 1 path, and `alembic current` on the copy shows `0001_audit_event`.
- [x] BE-1.2 Migration `0002_requisitions`. It creates:
  - `requisition` (Data Model §4.1 + `business_unit_key`, unique
    `(hr_system_key, external_requisition_id)`);
  - `requisition_snapshot` (§4.2);
  - `requisition_snapshot_payload` (**PROPOSED (D-05)**);
  - `screening_run` (§4.3 with the **PROPOSED (D-10)** deviations, index
    `(requisition_id, status, started_at)`);
  - `integration_attempt` (§4.17, index `(screening_run_id, integration_name, outcome)`).

  `status` is a string checked by the application enum, with no DB CHECK, so later
  states stay additive. `downgrade()` drops these five tables in reverse FK order.
  Done-when: `test_migration_round_trip` passes with `0002` at head, and `test_schema.py::test_requisition_unique_external_id` raises IntegrityError on a duplicate.
- [x] BE-1.3 `requisitions` models and scoped repositories. Add `RequisitionRepository`
  (`upsert` via `INSERT … ON CONFLICT (hr_system_key, external_requisition_id) DO UPDATE`
  of source fields only), `SnapshotRepository` and `ScreeningRunRepository`.
  `ScreeningRunRepository.get_for_principal(run_id, principal)` applies the
  **PROPOSED (D-09)** filter. The only unscoped read is `get_for_workflow(run_id)`, which
  services may use but routers never import. `claim_for_ingestion(run_id)` is a
  conditional `UPDATE … WHERE status='created' RETURNING`.
  Done-when: `test_run_scoping.py::test_principal_cannot_read_other_business_unit_run` and `test_run_scoping.py::test_claim_is_single_winner` pass.
- [x] BE-1.4 `integrations` module: HR System adapter contract and mock. Add an
  `HRSystemAdapter` protocol with `get_requisition(external_requisition_id) ->
  HRRequisitionPayload`, typed errors (`RequisitionNotFound`, `HRSystemUnavailable`,
  `InvalidHRResponse`), and a pydantic validation schema for the payload. Add
  `MockHRSystemAdapter`, which reads JSON fixtures from
  `integrations/adapters/hr_system/fixtures/` (layout in **PROPOSED (D-13)**). Fixtures:
  - `REQ-OPEN-1` complete and open;
  - `REQ-CLOSED-1`;
  - `REQ-INCOMPLETE-1` with no description;
  - `REQ-OTHER-BU-1` in business unit `bu-other`;
  - `REQ-UNAVAILABLE` raises `HRSystemUnavailable`;
  - `REQ-MALFORMED` fails schema validation;
  - any other ID raises not found.

  An adapter factory selects by `HR_SYSTEM_ADAPTER` and honours a per-call timeout. Every
  call writes an `integration_attempt` row (operation, correlation_id, attempt_number=1,
  outcome, error_code; no payload body).
  Done-when: `test_hr_mock_adapter.py::test_fixture_outcomes` covers all seven fixture cases, and `test_hr_mock_adapter.py::test_integration_attempt_recorded_without_payload` passes.
- [x] BE-1.5 Snapshot store (**PROPOSED (D-05)**). The `SnapshotStore` interface has
  `put(payload) -> (payload_reference, payload_hash)` and `get(reference,
  expected_hash)`. `DbSnapshotStore` writes canonical JSON (sorted keys, UTF-8, compact
  separators) and computes `sha256:<hex>`. `get` recomputes the hash and raises
  `SnapshotIntegrityError` on a mismatch. When the hash equals the requisition's latest
  snapshot hash, the existing snapshot is reused. `schema_version` comes from constant
  `REQUISITION_INGESTION_SCHEMA_VERSION = "1"`.
  Done-when: `test_snapshot_store.py::test_hash_is_canonical_and_verified`, `test_snapshot_store.py::test_tampered_payload_raises`, and `test_snapshot_store.py::test_identical_payload_reuses_snapshot` pass.
- [x] BE-1.6 Eligibility rules (**PROPOSED (D-07)**). A pure function
  `check_eligibility(payload, eligible_statuses) -> EligibilityResult(eligible,
  reason_code, missing_fields, rules_version)` lives in `requisitions/service.py`, with
  the rules in `constants.py`. Setting `REQUISITION_ELIGIBLE_SOURCE_STATUSES` defaults to
  `["open"]`. The function never fills defaults.
  Done-when: `test_eligibility.py::test_open_complete_eligible`, `test_eligibility.py::test_closed_not_eligible`, and `test_eligibility.py::test_missing_title_or_description_incomplete` pass.
- [x] BE-1.7 Run creation and ingestion services. `ScreeningRunService.create(principal,
  external_requisition_id, correlation_id)` inserts a run in `created` and writes the
  `ScreeningRunCreated` audit event (actor = principal) in the same transaction.
  `IngestionService.ingest(run_id)` claims the run (a no-op if the claim is lost) and moves
  it to `ingesting_requisition`. It then calls the adapter. If the requisition's business
  unit is outside the starter's scope, it blocks with `requisition_not_found` and stores
  nothing (D-09). Otherwise it upserts `requisition` and puts the snapshot, pins
  `requisition_id`, `requisition_snapshot_id` and `business_unit_key`, and checks
  eligibility. Then it either moves the run to `role_brief_draft` or to `blocked` with
  `completion_reason`, `status_details` and `completed_at`.

  Every status change writes an audit event (actor_type `system`, actor_id
  `requisitions.ingestion`, the run's correlation_id, and the reason_code) in the same
  transaction as the change (**PROPOSED (D-12)**). Closed and incomplete requisitions are
  still snapshotted and pinned for traceability. Not-found, inaccessible, unavailable and
  malformed responses create no requisition or snapshot.
  Done-when: `test_ingestion.py` passes with one test per fixture outcome (open→`role_brief_draft`; closed, incomplete, not found, other-BU, unavailable and malformed→`blocked` with the D-07/D-09 reason code), plus `test_ingestion.py::test_every_transition_has_audit_event_in_same_transaction` and `test_ingestion.py::test_no_values_invented_for_missing_fields`.
- [x] BE-1.8 Alembic CLI DB-copy guard (**D-16 Accepted 2026-10-22 — build**; originally: build only if D-16 is
  accepted, otherwise strike it). Today the copy guard covers pytest only. `alembic/env.py`
  should apply the same `_copy`/`_test` rule whenever `ENVIRONMENT` is `development` or
  `test`. It refuses before connecting and prints the rejected database name. `staging`
  and `production` are not affected. Move the guard from `tests/db_guard.py` to
  `app/core/db_guard.py` so tests and Alembic share it, and keep `tests/db_guard.py` as a
  re-export so existing imports keep working (D-01). No migration and no new setting.
  Done-when: `tests/migrations/test_alembic_guard.py::test_alembic_refuses_non_copy_database_in_development` passes (it runs `command.current` with a non-copy URL and `ENVIRONMENT=development`, expects a refusal, and confirms no connection was opened), and `test_migration_round_trip` still passes.

- [x] **Phase 1 Done-when:** in the Phase 1 worktree against the copy, the engineer reports
real output with every check passing: `ruff check`, `mypy app`, `pytest`, and `alembic
upgrade head && alembic downgrade -1 && alembic upgrade head`.

**Verified 2026-10-22 (MVP-light, D-18; solution-architect).** Code is in `backend/`
(branch `claude/keen-mayer-npaib1` at `add315f`; worktree
`/home/user/HR_phase1-worktrees/p1req-phase1` at `add315f` on
`feature/p1-requisitions-phase1`). Light check per D-18: every Done-when test function
exists under its exact name in the named file (Grep), and the orchestrator's run shows the
suite passing. Assertions were not audited line by line.
- `ruff check .`: All checks passed. `mypy app`: no issues in 38 source files.
  `pytest -q`: 59 passed.
- `alembic upgrade head; downgrade -1; upgrade head`: `0002_requisitions → 0001_audit_event
  → 0002_requisitions`. `alembic current` ends at `0002_requisitions (head)`.
- The BE-1.8 guard works from the CLI: with `ENVIRONMENT=development` and DB `hr_phase1`,
  `alembic current` refused with "the name must end in _copy or _test (D-03)".
- D-17 lockfiles are committed. There are no forward-migration drops and no tracked `.env`.
- `test_ingestion.py` has one test per fixture outcome (open, closed, incomplete, not
  found, other-BU, unavailable, malformed) plus the two named tests.
- Engineer deviation: `screening_run.scope_business_units` and the related scope rules are
  not covered by any accepted decision. They are written up as D-19 (Accepted 2026-10-22). The ticks
  stand because the column is additive and round-trips, but D-19 needs approval before
  Phase 2 relies on it.

**Reversibility:** Phase 1 adds no routes, so a running app behaves exactly as Phase 0.
`alembic downgrade 0001_audit_event` removes the five tables. Audit rows written by tests
remain in `audit_event`, which is append-only by design. To remove the code, revert the
branch.

**Deferred from Phase 1:**
- Real HR System adapter (product not confirmed; Tech Arch §15.1).
- Pagination and authentication in the adapter (mock does not need them).
- Retries with backoff and `next_retry_at` use (the column exists; a single attempt is
  enough for a mock; D-06).
- Object-storage snapshot backend (D-05 seam).
- App-level payload encryption (open question Q-6).
- Re-ingestion when the source version changes (Tech Arch §5.1 design control; belongs
  with role_briefs).

---

### Phase 2 — Screening-run API and background execution

Goal: the acceptance criteria end to end over HTTP, behind `FEATURE_SCREENING_RUNS`.

**Testing level (D-18, MVP-light):** each Done-when names one focused test per behaviour.
Do not add exhaustive matrices or extra hardening tests. `ruff`, `mypy`, `pytest` and the
migration round trip stay mandatory. **Precondition (met 2026-10-22, D-19 Accepted):** D-19 (run scope capture) must be
approved before BE-2.3 and BE-2.4 rely on `scope_business_units`.

- [x] BE-2.1 Isolation setup (D-03). Create worktree
  `/home/user/HR_phase1-worktrees/p1req-phase2` on branch `feature/p1-requisitions-phase2`,
  based on the reviewed Phase 1 branch. The copy DB is migrated to `0002_requisitions`.
  Done-when: the report shows `git worktree list` with the Phase 2 path, and `alembic current` on the copy shows `0002_requisitions`.
- [x] BE-2.2 Run executor (**PROPOSED (D-06)**). Add a `RunExecutor` interface with
  `dispatch(run_id)`. `InProcessExecutor` uses an asyncio task with its own DB session,
  started only after the request's transaction commits, and it tracks and awaits tasks on
  shutdown. `InlineExecutor` is for tests. Setting `RUN_EXECUTOR` takes `in_process` (the
  default) or `inline`. On startup, recovery re-dispatches runs in `created`. It blocks
  runs that have stayed in `ingesting_requisition` longer than
  `INGESTION_STALE_AFTER_SECONDS` (default 600), with reason `ingestion_interrupted` and an
  audit event. If `FEATURE_SCREENING_RUNS=true` and `HR_SYSTEM_ADAPTER` is unset, startup
  fails.
  Done-when: `test_executor.py::test_dispatch_after_commit_only`, `test_executor.py::test_startup_recovery_redispatches_created_and_blocks_stale`, and `test_executor.py::test_double_dispatch_ingests_once` pass.
- [x] BE-2.3 `POST /api/v1/screening-runs`. Permission: `screening_run:create`
  (**PROPOSED (D-08)**). Body: `{"external_requisition_id": str}`, 1–128 chars, trimmed,
  extra fields forbidden (**PROPOSED (D-11)**). The response is `202 Accepted` with body
  `{run_id, status: "created", status_url, correlation_id}`, a `Location` header and an
  `X-Correlation-ID` header. Validation errors return 422. The router calls only
  `ScreeningRunService` and the executor. It never calls a repository. The route is mounted
  only when `FEATURE_SCREENING_RUNS=true`.
  Done-when: `test_api_screening_runs.py::test_post_returns_202_with_run_id_and_status_url`, `test_api_screening_runs.py::test_post_without_principal_401`, and `test_api_screening_runs.py::test_post_without_permission_403` pass.
- [x] BE-2.4 `GET /api/v1/screening-runs/{run_id}`. Permission: `screening_run:read`
  (**PROPOSED (D-08)**). The row is scoped through
  `ScreeningRunRepository.get_for_principal`. A run that is missing or out of scope
  returns 404 (D-09). The response follows **PROPOSED (D-11)**: `run_id`, `status`,
  `phases` (phase 1 status derived from the run status), `completion_reason`,
  `status_details`, `requisition` ({external_requisition_id, hr_system_key, requisition_id,
  snapshot_id, payload_hash, captured_at}, or null), `started_at`, `completed_at` and
  `correlation_id`. It never includes the raw payload.
  Done-when: `test_api_screening_runs.py::test_get_returns_state_and_phase_status`, `test_api_screening_runs.py::test_get_other_business_unit_404`, and `test_api_screening_runs.py::test_get_without_permission_403` pass.
- [x] BE-2.5 End-to-end acceptance tests over HTTP (`RUN_EXECUTOR=inline`). Trimmed
  2026-10-22 under D-18 (MVP-light): one focused test per behaviour, covering the happy
  path and one blocked case.
  - Happy path: POST `REQ-OPEN-1` → 202, the run reaches `role_brief_draft`, and GET shows
    `role_brief_draft`.
  - Blocked: POST `REQ-CLOSED-1` → 202, and GET shows
    `blocked/requisition_not_eligible_status`.
  - 401/403: covered by the BE-2.3 tests `test_post_without_principal_401` and
    `test_post_without_permission_403`. They are not duplicated here.

  Incomplete, not-found, other-BU, unavailable and malformed outcomes are already covered
  at service level by `test_ingestion.py` (BE-1.7) and are not repeated over HTTP.
  Done-when: `test_e2e_screening_runs.py::test_open_requisition_reaches_role_brief_draft` and `test_e2e_screening_runs.py::test_closed_requisition_is_blocked` pass, together with the BE-2.3 401/403 tests.
- [x] BE-2.6 Safe server access log (Tech Arch §6.2, §9; Phase 0 deviation e). Uvicorn's
  own access log prints query strings, but the app's request log does not. Add
  `--no-access-log` to the `uvicorn` command in `scripts/start-backend.sh`. The app's
  `app.request` JSON log, which records method, path, status, duration and correlation ID,
  then becomes the only access log. This changes only one flag in the dev script, and
  removing the flag reverts it.
  Done-when: during the Phase 2 manual curl check, `GET /healthz?probe=secret-value` against `scripts/start-backend.sh` prints a JSON `app.request` line, and the console contains neither `secret-value` nor a uvicorn access-log line (console excerpt in the report).

- [x] **Phase 2 Done-when:** in the Phase 2 worktree against the copy, the engineer reports
real output with every check passing: `ruff check`, `mypy app`, `pytest`, and `alembic
upgrade head && alembic downgrade -1 && alembic upgrade head`. In addition, a manual
`curl` POST and GET against `scripts/start-backend.sh` (with `FEATURE_SCREENING_RUNS=true`,
`AUTH_MODE=dev_header` and `HR_SYSTEM_ADAPTER=mock`) shows 202 followed by
`role_brief_draft` for `REQ-OPEN-1`.

**Verified 2026-10-22 (MVP-light, D-18; solution-architect).** Phase 2 is merged to
`master` at `a1d9b85`. Light check per D-18: Grep confirms that every Done-when test exists
under its exact name in the named file in `backend/tests/`. Assertions were not audited
line by line.
- `test_executor.py` has the three BE-2.2 tests.
- `test_api_screening_runs.py` has the six BE-2.3 and BE-2.4 tests.
- `test_e2e_screening_runs.py` has `test_open_requisition_reaches_role_brief_draft` and
  `test_closed_requisition_is_blocked`.

The worktree `/home/user/HR_phase1-worktrees/p1req-phase2` exists. The routes are gated by
`FEATURE_SCREENING_RUNS` (`app/main.py`), and the permissions `screening_run:create` and
`screening_run:read` are defined in `requisitions/constants.py`. `--no-access-log` is
present in `scripts/start-backend.sh` and `scripts/start-backend.ps1`.

The orchestrator's run in the Phase 2 worktree:
- `ruff check .`: All checks passed.
- `mypy app`: no issues in 38 source files.
- `pytest`: 70 passed.
- `alembic downgrade -1` and `upgrade head` ran clean, and `alembic current` shows
  `0002_requisitions (head)`.

Engineer-reported manual checks:
- BE-2.6: the console showed only `app.request` JSON lines. A grep for `secret-value`
  found 0 lines, and a grep for uvicorn access lines found 0.
- Curl smoke: POST `REQ-OPEN-1` returned 202, and GET returned `role_brief_draft`.

**Reversibility:** setting `FEATURE_SCREENING_RUNS=false` (the default) unmounts both
routes and disables executor startup recovery, so the app behaves exactly as after Phase
1. Phase 2 adds no migration. Existing runs, snapshots and audit events stay in the
database untouched. Runs that were mid-ingestion when the flag was turned off are
recovered as `blocked/ingestion_interrupted` the next time the flag is enabled.

**Deferred from Phase 2:**
- `Idempotency-Key` on POST and any rule against concurrent active runs for one
  requisition (open question Q-3).
- Queue worker (Celery/RQ + Redis) and transactional outbox (D-06; not needed for one
  in-process executor).
- Cancel-run endpoint (`cancelled` state; not in the acceptance criteria).
- Rate limiting and request-size limits.
- OpenAPI export and TypeScript type generation (no frontend in this feature).
- A frontend status page (kickoff default is none).
- Dropped from BE-2.5 under D-18 (MVP-light), to revisit before pilot/production: HTTP
  end-to-end tests for incomplete and not-found requisitions, the HTTP-level audit-trail
  test (actor, timestamp, correlation_id equal to the POST's `X-Correlation-ID`), and the
  `FEATURE_SCREENING_RUNS=false` → 404 route test. The flag still defaults to off.

---

### Feature-level deferred list

| Item | Reason |
|---|---|
| `role_briefs` module, AI extraction, `awaiting_role_approval`, approve endpoint | Out of scope (next feature). Runs stop at `role_brief_draft`. |
| Phase 2 configuration, candidates, Fusion Mind | Out of scope per kickoff. |
| Real HR System adapter | Product not confirmed. The mock sits behind the `HRSystemAdapter` seam. |
| Production SSO | Out of scope. `PrincipalProvider` fails closed by default. |
| Frontend (all FE tasks) | Kickoff default is none, and acceptance is API-only. |
| `workflow_events` table | `audit_event` covers state transitions. Add only when an outbox or queue is introduced. |
| Object storage, app-level encryption, retention automation | Open hosting and retention decisions (Tech Arch §15.5, §15.7). D-05 keeps a seam. |
| PCS memory import | D-0 is still open. A checkpoint markdown is written under `docs/checkpoints/` after each phase. |

### Open questions for approval

**Resolved 2026-10-22:** the user approved every default below. Q-8: Python 3.12 and PostgreSQL 16 are present in the cloud build container; confirm separately for local machines.

- **Q-1** Approve or amend each PROPOSED decision D-05 to D-13 in `docs/DECISIONS.md`.
- **Q-2** Does the platform serve several business units? Which HR System field will
  carry the business unit? D-09 assumes `business_unit` exists in the payload. If there is
  a single BU, D-09 still works with one configured key.
  **Still open in practice (2026-10-22, D-19):** the build requires `business_unit` in
  the payload. If it is missing or is `*`, the run is blocked as `hr_response_invalid`.
- **Q-3** Should a second POST for a requisition that already has an active run be
  allowed? The default is yes, with no idempotency key. The alternative is 409 or
  returning the existing run.
- **Q-4** Which HR System statuses are eligible? The default is `["open"]`. Should
  `on_hold` block, or hold the run (System Design §5 says "stop or hold")? The default is
  `blocked`, as the kickoff states.
- **Q-5** Is title + description + an eligible status the right minimum for eligibility
  (D-07), or must responsibilities, seniority or location also be present?
- **Q-6** Do snapshot payloads in dev need app-level encryption, or is database
  encryption at rest acceptable until hosting is chosen? The default is no app-level
  encryption in dev; production is not enabled by this plan.
- **Q-7** Confirm the audit immutability policy (Data Model §10.9). The default is a DB
  trigger blocking UPDATE and DELETE (D-12).
- **Q-8** Confirm the local toolchain: Python 3.12 and PostgreSQL 16 available on the
  build machine, with `backend/.venv` per `scripts/start-backend.sh`.
- **Q-9** Should the response to an out-of-scope requisition stay indistinguishable from
  not found (`requisition_not_found`)? That is the default. The audit records the true
  reason code `requisition_not_accessible`.

---

## Feature: MVP UI — screening runs

- **Kickoff:** `docs/prompts/kickoffs/2026-10-22-mvp-ui.md`
- **Plan status:** APPROVED by the user, 2026-10-22 — all defaults accepted; D-21…D-25 Accepted. D-20 is Accepted (user decisions).
  D-21…D-25 are "Proposed — awaiting approval". The defaults below make the plan buildable.
  If approval changes a default, I amend the affected tasks before the build starts.
- **Plan author:** solution-architect, 2026-10-22
- **Delivery status:** COMPLETE for local dev (2026-10-22, merged at `e21aa1f`). Hosting is
  deferred (D-20).
  Q-12 (the Windows `.ps1` check) is still pending with the user.
- **Specs and decisions used:** Technical Architecture §2 (frontend: React + TypeScript),
  §4.1, §6.1–6.2, §9. D-08 (dev principal headers), D-11 (API contract and flag), D-14
  (no served OpenAPI), D-18 (MVP-light testing), D-20…D-25.
- **Starting point:** No `frontend/` exists. `scripts/start-frontend.sh` and `.ps1` already
  run `cd frontend && rm -rf .next && npm run dev -- --port <port>`. The backend has no
  CORS middleware and serves no `/openapi.json` (D-14). Auth is `AUTH_MODE=dev_header`
  (`X-Dev-Principal-Id`, `X-Dev-Permissions`, `X-Dev-Business-Units`). Mock fixtures
  `REQ-OPEN-1`, `REQ-CLOSED-1` and `REQ-INCOMPLETE-1` are in business unit `bu-1`, and
  `REQ-OTHER-BU-1` is in `bu-other`.
- **API contract the UI builds against:** Requisitions Phase 2 BE-2.3 and BE-2.4 as
  written above, plus D-11. POST `/api/v1/screening-runs` takes
  `{"external_requisition_id"}` (1–128 chars, trimmed, extra fields forbidden) and returns
  202 `{run_id, status, status_url, correlation_id}`. GET `/api/v1/screening-runs/{run_id}`
  returns `run_id, status, phases, completion_reason, status_details, requisition,
  started_at, completed_at, correlation_id`. Both routes exist only when
  `FEATURE_SCREENING_RUNS=true`. Phase 2 is being built now in a separate worktree, so
  this feature does not edit or tick anything in the Requisitions section.
- **Task ID scheme:** plan phase numbers are one global sequence, so IDs never collide.
  The Requisitions feature used Phases 0–2 (BE-0.x…BE-2.x). This feature uses
  **Phase 3** and **Phase 4** (FE-3.x, BE-3.x, FE-4.x, BE-4.x). These are delivery-plan
  phases. They are not the System Design "Phases 1–4" (role brief, 3A/3B and so on).
  I did not use a `BE-UI.n` scheme because the ID rule is `BE-<phase>.<n>` with a phase
  number.
- **Testing level (D-18, MVP-light, user instruction):** `npm run build`, `npm run lint`
  and `npm run typecheck` are mandatory for every FE task. Backend tasks keep `ruff check
  .`, `mypy app` and `pytest`. Behaviour is checked with at most one manual check per
  behaviour, as named in each Done-when. This feature adds no frontend test runner.
  It has no migration, so there is no round trip to run.

### Standing-rule compliance (applies to every task below)

- **D-01:** Everything is new (`frontend/`, `backend/scripts/`, `backend/openapi.json`).
  No backend route, schema or existing script changes. `scripts/start-frontend.*` stay
  unchanged.
- **D-02:** The screens are behind `NEXT_PUBLIC_FEATURE_SCREENING_RUNS` (default `false`).
  The dev principal picker is behind `NEXT_PUBLIC_DEV_AUTH` (default `false`). The backend
  flag `FEATURE_SCREENING_RUNS` still gates the API. The UI never deletes anything.
- **D-03:** Each phase starts with its own worktree under `/home/user/HR_phase1-worktrees/`.
  The backend used for manual checks runs from that worktree against the copy
  `hr_phase1_mvpui_copy`. It never uses the live dev DB, and it never uses
  `hr_phase1_p1req_copy` while the Requisitions Phase 2 build is using it.
- **D-04:** The UI adds no endpoint. Every call goes to an existing backend route that
  already declares its permission (`screening_run:create`, `screening_run:read`). Row
  scoping stays in the backend repository. The UI hides nothing for security. It shows
  the backend's 401/403/404 as messages.

---

### Phase 3 — Frontend foundation (scaffold, design system, API path, types, dev principal)

Goal: a runnable Next.js app in `frontend/` that `scripts/start-frontend.*` start
unchanged. It has the in-repo components, a same-origin proxy to the backend, generated
API types and the dev-only principal picker. It has no screening-run screens yet.
**Precondition:** none. It can be built in parallel with Requisitions Phase 2.

- [x] FE-3.1 Isolation setup (D-03). Create worktree
  `/home/user/HR_phase1-worktrees/mvp-ui-phase3` on branch `feature/mvp-ui-phase3`, based
  on the current reviewed integration branch (the branch holding Requisitions Phase 1).
  Create the database `hr_phase1_mvpui_copy` and migrate it to that branch's head with
  `backend/.env` in the worktree pointing at it.
  Done-when: the report shows `git worktree list` with the Phase 3 path, `psql -l` listing `hr_phase1_mvpui_copy`, and `alembic current` on it.
- [x] BE-3.1 OpenAPI export script (**PROPOSED (D-23)**). Add
  `backend/scripts/export_openapi.py`. It builds the app with
  `create_app(Settings(DATABASE_URL=<placeholder>, ENVIRONMENT=development,
  FEATURE_SCREENING_RUNS=True, HR_SYSTEM_ADAPTER="mock"))` so feature-flagged routes
  appear. It does not run the lifespan and opens no DB connection. It writes
  `app.openapi()` to `backend/openapi.json` as indented JSON with sorted keys, and the
  file is committed. It mounts no route, so D-14 and the route audit are unchanged.
  Done-when: `cd backend && python scripts/export_openapi.py` writes `backend/openapi.json` whose `paths` contain `/healthz`, and `ruff check .`, `mypy app` and `pytest` still pass.
- [x] FE-3.2 Scaffold `frontend/` (**D-20**, **PROPOSED (D-25)**). Use Next.js App Router
  and TypeScript (`strict`), with `src/app/`, Tailwind CSS, ESLint (flat config with the
  Next.js rules) and a committed `package-lock.json`. Use the current stable Next.js major
  at scaffold time, and declare Node ≥ 20 in `engines`. Scripts: `dev`, `build`, `start`,
  `lint` (ESLint CLI), `typecheck` (`tsc --noEmit`), `gen:api`. Add `frontend/.env.example`
  with `BACKEND_URL=http://localhost:8000`, `NEXT_PUBLIC_DEV_AUTH=false` and
  `NEXT_PUBLIC_FEATURE_SCREENING_RUNS=false`. `.env*.local` stays untracked. The home page
  is a placeholder. `scripts/start-frontend.sh` and `.ps1` are not modified.
  Done-when: `scripts/start-frontend.sh` serves the placeholder home page on http://localhost:3000 (manual check), and `npm run build`, `npm run lint` and `npm run typecheck` pass.
- [x] FE-3.3 Minimal design system (**D-20**). Tailwind theme tokens (colour, spacing,
  radius, font sizes) go in `src/app/globals.css`. Add seven components in
  `src/components/ui/`, exported from `index.ts`: `PageShell`, `Card`, `Button`,
  `TextField`, `Alert` (info/success/warning/error), `StatusBadge` and `KeyValueList`.
  Text is rendered as escaped data only, with no `dangerouslySetInnerHTML`. The
  placeholder home page uses `PageShell` and `Card`.
  Done-when: `npm run build`, `npm run lint` and `npm run typecheck` pass, and Grep shows no `dangerouslySetInnerHTML` under `frontend/src`.
- [x] FE-3.4 Same-origin API path and typed client (**PROPOSED (D-22)**, **PROPOSED
  (D-23)**). In `next.config.ts`, rewrite `/api/v1/:path*` and `/healthz` to
  `${BACKEND_URL}`, with default `http://localhost:8000`. `npm run gen:api` runs
  `openapi-typescript ../backend/openapi.json -o src/api/schema.d.ts`, and the generated
  file is committed and never hand-edited. `src/api/client.ts` is a thin `fetch` wrapper.
  It returns `{ok: true, status, data, correlationId}` or `{ok: false, status, error,
  correlationId}`, and network failures map to `status: 0`. No backend change and no CORS.
  Done-when: with the backend running from the worktree, `curl -s http://localhost:3000/healthz` returns `{"status":"ok"}` through the proxy (manual check), and `npm run gen:api` followed by `git status` shows no diff in `src/api/schema.d.ts`.
- [x] FE-3.5 Dev-only principal picker (**PROPOSED (D-21)**). `src/dev-auth/` holds the
  presets, stored in `localStorage`:
  - "No principal" (the default; sends no headers);
  - "Recruiter bu-1" (`screening_run:create,screening_run:read`, `bu-1`);
  - "Viewer bu-1" (`screening_run:read`, `bu-1`);
  - "Recruiter bu-other" (`screening_run:create,screening_run:read`, `bu-other`).

  When `NEXT_PUBLIC_DEV_AUTH=true` and `NODE_ENV !== "production"`, the picker appears
  in `PageShell` and the client adds the three `X-Dev-*` headers. Otherwise the client
  sends no `X-Dev-*` header. `next.config.ts` throws during production build or production
  server start when `NEXT_PUBLIC_DEV_AUTH=true`.
  Done-when: `NEXT_PUBLIC_DEV_AUTH=true npm run build` exits non-zero with the D-21 message and `npm run build` with the flag unset passes; in `npm run dev` the picker is visible with the flag `true` and absent when it is unset (manual check).

- [x] **Phase 3 Done-when:** in the Phase 3 worktree, the engineers report real output with
  every check passing: `npm run build`, `npm run lint`, `npm run typecheck` (frontend), and
  `ruff check .`, `mypy app`, `pytest` (backend). `scripts/start-frontend.sh` serves the
  home page. The `.ps1` script is unchanged, and the user checks it once on Windows
  (Q-12). *(The Windows `.ps1` check, Q-12, is still pending with the user.)*

**Verified 2026-10-22 (MVP-light, D-18).** Merged at `8a0a973`. Files confirmed by
Glob/Grep: `backend/scripts/export_openapi.py`; `backend/openapi.json` with paths
`/healthz`, `/api/v1/screening-runs` and `/api/v1/screening-runs/{run_id}`;
`frontend/package.json` with scripts `dev/build/start/lint/typecheck/gen:api` and
`engines.node ">=20"`; `frontend/next.config.ts` with `rewrites()` and the D-21 production
refusal; `frontend/src/components/ui/` with the seven components and `index.ts`;
`frontend/src/api/client.ts` and `schema.d.ts`; `frontend/src/dev-auth/` (picker, presets,
store, config). Grep finds no `dangerouslySetInnerHTML` under `frontend/src`. Reported output:
orchestrator ran `npm run build`, `lint` and `typecheck` (exit 0) and
`NEXT_PUBLIC_DEV_AUTH=true npm run build` (exit 1). Backend reported ruff clean, mypy (38
files) clean, pytest 70 passed, `alembic current` 0002_requisitions (head) on
`hr_phase1_mvpui_copy`, the export re-run gave no diff, and `git worktree list` and `psql -l`
were shown. Frontend reported manual checks: `start-frontend.sh` served the home page on :3000,
`/healthz` through the proxy returned `{"status":"ok"}`, `gen:api` left no diff, the D-21
refusal message was shown, and the picker showed with the flag on and was absent with it unset.
Deviations: kept the Next 16 scaffold config flags; removed `next/font/google` (no network
fonts) and the demo SVGs; committed the scaffold `AGENTS.md` (Next.js agent note); the picker
lives in `src/dev-auth/`, not `ui/`; FE-3.2 to FE-3.5 landed in one commit; BE-3.1 already
exports the screening-run routes, which covers most of BE-4.1. Still open: Q-12 (Windows
`.ps1` check, the user's).

**Reversibility:** everything is new. Nothing in the backend imports `backend/scripts/` or
reads `backend/openapi.json`. To roll back, remove the worktree or revert the branch.
Without `frontend/`, `scripts/start-frontend.*` fail exactly as they do today. The dev
picker is off by default, and production builds refuse it. No data or schema state is
left behind.

**Deferred from Phase 3:** frontend test runner (Vitest/Playwright, D-18); CI check that
`openapi.json` and `schema.d.ts` match the code (hardening); served `/docs` (D-14); CSP
and security headers (no hosting yet); dark mode and theming beyond the tokens.

---

### Phase 4 — Screening-run screens (start a run, run status with polling)

Goal: the kickoff acceptance in a browser. (1) Start a run from an HR requisition ID.
(2) A run status page that refreshes until `role_brief_draft` or `blocked`. (3) Clear
401/403/404/422 messages.
**Precondition:** Requisitions Phase 2 (BE-2.1…BE-2.6) is verified, ticked and merged
into the integration branch, and Phase 3 is reviewed.

- [x] FE-4.1 Isolation setup (D-03). Create worktree
  `/home/user/HR_phase1-worktrees/mvp-ui-phase4` on branch `feature/mvp-ui-phase4`, based
  on the integration branch with Phase 3 and Requisitions Phase 2 merged. Migrate
  `hr_phase1_mvpui_copy` to head.
  Done-when: the report shows `git worktree list` with the Phase 4 path, and `alembic current` on `hr_phase1_mvpui_copy` shows `0002_requisitions (head)`.
- [x] BE-4.1 Re-export the OpenAPI schema with the Phase 2 routes. Run
  `backend/scripts/export_openapi.py` and commit `backend/openapi.json`. There is no code
  change.
  Done-when: Grep shows `/api/v1/screening-runs` and `/api/v1/screening-runs/{run_id}` under `paths` in `backend/openapi.json`.
- [x] FE-4.2 Screening-run API functions. Run `npm run gen:api`. Add
  `src/api/screening-runs.ts` with `createScreeningRun(externalRequisitionId)` and
  `getScreeningRun(runId)`, typed only from `src/api/schema.d.ts`. Add
  `src/api/messages.ts`, which maps responses to user messages:
  - 401 "No signed-in user. Pick a dev principal.";
  - 403 "You do not have permission (`<permission>`).";
  - 404 on POST "Screening runs are not enabled on the backend.";
  - 404 on GET, or 422 on GET for a malformed ID, "Run not found, or you cannot see it.";
  - 422 on POST shows the server's field message(s) from `detail[].msg`;
  - 0 or 5xx "Backend unavailable. Try again." with the correlation ID.

  The `completion_reason` labels cover the D-07 codes, and an unknown code is shown raw.
  Done-when: `npm run typecheck` passes and Grep finds no hand-written screening-run request/response type (`type|interface .*ScreeningRun`) under `frontend/src` outside `src/api/schema.d.ts`.
- [x] FE-4.3 Start-run page at `/` (behind `NEXT_PUBLIC_FEATURE_SCREENING_RUNS`; when it
  is `false`, the page shows an info `Alert` "Screening runs are turned off"). The page
  has one `TextField` (HR requisition ID, required, no client-side length cap so the
  server's 422 is shown) and a `Button` that is disabled while submitting. On 202 it
  navigates to `/screening-runs/<run_id>`. Errors appear in an `Alert` from FE-4.2.
  Done-when: manual check against the Phase 4 backend: "Recruiter bu-1" + `REQ-OPEN-1` lands on `/screening-runs/<run_id>`; "No principal" shows the 401 message; "Viewer bu-1" shows the 403 message; a 129-character ID shows the server's 422 message.
- [x] FE-4.4 Run status page `/screening-runs/[runId]` (same flag). It shows:
  - a `StatusBadge` for `status` and one for `phases.phase_1`;
  - the `completion_reason` label and `status_details.missing_fields` when present;
  - the pinned requisition (`external_requisition_id`, `hr_system_key`, `requisition_id`,
    `snapshot_id`, `payload_hash`, `captured_at`), or "Not pinned yet / not pinned";
  - `started_at`, `completed_at` and `correlation_id`;
  - a manual "Refresh" button.

  Polling follows **PROPOSED (D-24)**. Errors use the FE-4.2 messages, and the raw
  snapshot payload is never requested or shown.
  Done-when: manual check: a `REQ-OPEN-1` run shows `role_brief_draft`, phase 1 `in_progress` and the pinned requisition, and the backend `app.request` log shows no further GETs for that run after the status is reached; a `REQ-CLOSED-1` run shows `blocked` with the `requisition_not_eligible_status` label; the same `REQ-OPEN-1` URL opened with "Recruiter bu-other" shows the not-found message.

- [x] **Phase 4 Done-when:** in the Phase 4 worktree, `npm run build`, `npm run lint` and
  `npm run typecheck` pass. Backend `ruff check .`, `mypy app` and `pytest` pass. One
  manual walkthrough covers acceptance (1)–(3), and the report includes screenshots or a
  console excerpt. The backend is started with `scripts/start-backend.sh` from the
  worktree (`FEATURE_SCREENING_RUNS=true`, `AUTH_MODE=dev_header`,
  `HR_SYSTEM_ADAPTER=mock`, DB `hr_phase1_mvpui_copy`). The frontend is started with
  `scripts/start-frontend.sh` (`NEXT_PUBLIC_DEV_AUTH=true`,
  `NEXT_PUBLIC_FEATURE_SCREENING_RUNS=true`).

**Verified 2026-10-22 (MVP-light, D-18; solution-architect).** Merged at `e21aa1f`. Files
confirmed by Glob/Grep: `frontend/src/api/screening-runs.ts` (`createScreeningRun`,
`getScreeningRun`); `frontend/src/api/messages.ts` (401, POST-404, not-found and
backend-unavailable messages); `frontend/src/features.ts`
(`NEXT_PUBLIC_FEATURE_SCREENING_RUNS`); `frontend/src/app/page.tsx` (the start form);
`frontend/src/app/screening-runs/[runId]/page.tsx` and `RunStatusView.tsx`. Grep finds no
`(type|interface) .*ScreeningRun` under `frontend/src` outside `schema.d.ts`, and no
`dangerouslySetInnerHTML`. `backend/openapi.json` has `/api/v1/screening-runs` and
`/api/v1/screening-runs/{run_id}`. Reported output: the orchestrator ran `npm run build`,
`lint` and `typecheck` (exit 0), ruff ("All checks passed!") and pytest ("70 passed in 3.50s")
in the Phase 4 worktree. The engineer reported `alembic current` 0002_requisitions (head) on
`hr_phase1_mvpui_copy`, and no diff after re-running `export_openapi` or `gen:api`. The
engineer also ran a Playwright walkthrough with the Phase 4 Done-when settings, with seven
screenshots in the session scratchpad:
- `REQ-OPEN-1` reached `/screening-runs/<id>` with `role_brief_draft`, phase_1 `in_progress`
  and the pinned requisition. The backend log showed no further GETs for that run in the 10 s
  after.
- `REQ-CLOSED-1` showed blocked, "Requisition is not in an eligible status".
- No principal showed the 401 message.
- Viewer bu-1 showed "You do not have permission (screening_run:create)."
- A 129-character ID showed "String should have at most 128 characters".
- Recruiter bu-other on the open run URL showed "Run not found, or you cannot see it."

The orchestrator also reported, from `/home/user/HR_phase1-worktrees/mvp-ui-phase4/backend`:
`mypy app` gave "Success: no issues found in 38 source files", and `git worktree list` gave
"/home/user/HR_phase1-worktrees/mvp-ui-phase4  e21aa1f [feature/mvp-ui-phase4]".
Deviations:
- The 403 message uses the route's declared permission, because the backend 403 body is only
  "Forbidden".
- The run page is split into a server `page.tsx` and a client `RunStatusView.tsx` inside
  Suspense (Next 16 Cache Components).
- Dev StrictMode doubles the first GET. This happens in dev only.
- A 422 on GET stops polling.
- Unknown statuses show "Request failed (HTTP n)".
- Extra runs from dry runs remain in the copy DB. They are never deleted, by design.

**Feature status (MVP UI — screening runs): COMPLETE for local dev, 2026-10-22.** Hosting is deferred (D-20, local dev
only). Q-12 (the Windows `start-frontend.ps1` check) is still pending with the user.

**Reversibility:** `NEXT_PUBLIC_FEATURE_SCREENING_RUNS=false` (the default) turns the
screens into an "off" notice. Backend `FEATURE_SCREENING_RUNS=false` unmounts the API, and
the UI then shows "not enabled". There is no migration. Runs started through the UI are
ordinary runs created by the existing API. They stay in the copy DB and are never deleted.
Reverting the branch removes the pages and leaves the Phase 3 foundation.

**Deferred from Phase 4:**
- List-all-runs page. No list endpoint exists. Adding one is additive, but it needs a
  scoped repository list query, a permission, pagination and its own BE tasks, so it is
  not trivial. It goes to the next UI feature.
- Server push (SSE/WebSocket) instead of polling.
- Accessibility audit, i18n, and a design pass on the in-repo components.

### Feature-level deferred list (MVP UI)

| Item | Reason |
|---|---|
| Hosting / deployment of the frontend | User decision (D-20): local dev only. |
| Production SSO / login page | Out of scope. The dev picker is the only principal source, and production builds refuse it (D-21). |
| Role brief, candidates, evaluation, shortlist screens | Out of scope per kickoff. Their backend modules do not exist yet. |
| List-all-runs page | No backend endpoint (see Phase 4 deferred). |
| Frontend automated tests, OpenAPI drift check in CI | D-18 MVP-light. Revisit with D-18 before pilot. |
| CORS on the backend | Not needed with the same-origin proxy (D-22). |
| Any change to `Extension/` | Out of scope per kickoff. |

### Open questions for approval (MVP UI)

Numbered from Q-10 so they do not collide with the Requisitions Q-1…Q-9.

**Resolved 2026-10-22:** the user approved all defaults (Q-10…Q-14); D-21…D-25 Accepted. Q-11: Node 22 and npm 10 are present in the cloud build container; confirm separately for local machines. Q-12 (Windows run of `start-frontend.ps1`) stays a manual check for the user.

- **Q-10** Approve or amend D-21…D-25 (defaults above).
- **Q-11** Toolchain on local machines: Node ≥ 20 LTS and npm (the start scripts already
  use `npm`). Is pnpm or yarn wanted instead? The default is npm.
- **Q-12** `scripts/start-frontend.ps1` cannot be run in the Linux build container. Will
  you check it once on Windows after Phase 3? It is unchanged by this plan.
- **Q-13** Are the four dev principal presets (FE-3.5) enough, or do you also want free-text
  fields for ID, permissions and business units? The default is presets only.
- **Q-14** Should the start form be the home page `/`? The alternative is
  `/screening-runs/new` with `/` as a landing page. The default is `/`.
- **Q-15** Sequencing: Phase 3 can start now. Phase 4 waits for Requisitions Phase 2 to be
  verified and merged. Do you confirm?
  **Resolved 2026-10-22:** Requisitions Phase 2 is verified, ticked and merged to `master`
  (`a1d9b85`). The Phase 4 precondition is met, so Phase 4 may follow Phase 3 directly.
- **Q-16** `.claude/agents/frontend-engineer.md` still says "align to the design system
  bundle". Under D-20 the in-repo `frontend/src/components/ui/` set is that design system.
  The agent file is outside the architect's ownership. Should its owner update the wording
  to point at D-20?

---

## Feature: SQLite default database

- **Kickoff:** `docs/prompts/kickoffs/2026-10-22-sqlite-default.md`
- **Plan status:** APPROVED by the user, 2026-10-22 — all defaults accepted (Q-17…Q-21); D-27…D-30 Accepted. D-26 is Accepted (user decisions, 2026-10-22).
  D-27…D-30 are "Proposed — awaiting approval". The defaults below make the plan
  buildable. If approval changes a default, I amend the affected tasks before the build
  starts.
- **Plan author:** solution-architect, 2026-10-22
- **Starting point:** `master` = `6e1bc77`. PostgreSQL-specific code (verified by Grep and
  Read):
  - migrations `0001_audit_event` (`gen_random_uuid()`, `clock_timestamp()`, the plpgsql
    function, and the UPDATE/DELETE and TRUNCATE triggers) and `0002_requisitions`
    (JSONB, `ARRAY(String(64))` with default `'{}'::varchar[]`);
  - models in `audit`, `requisitions` and `integrations` (JSONB, ARRAY, and
    `server_default` text for UUIDs and timestamps);
  - `requisitions/repository.py` (`postgresql.insert … on_conflict_do_update`,
    `func.clock_timestamp()` in upsert and `transition`, and `func.make_interval` in
    `list_stale_ids`);
  - `scripts/dev_precheck.py` (asyncpg ping), `backend-start.bat` messages, and
    `backend/.env.example`.

  `app/core/db_guard.py` checks `make_url(url).database` for a `_copy`/`_test` suffix,
  which on SQLite would be a path such as `./x_copy.db` and so would always be refused.
  `tests/conftest.py` builds its own engine with `create_async_engine`.
- **Task ID scheme:** this continues the global phase sequence. Requisitions used Phases
  0–2 and MVP UI used Phases 3–4, so this feature is **Phase 5** (BE-5.x). One phase is
  enough.
- **Testing level (D-18):** `ruff check .`, `mypy app`, `pytest` and the migration round
  trip, on SQLite and once on PostgreSQL. The phase adds two tests
  (`test_foreign_keys_are_enforced` and `test_sqlite_file_name_must_be_copy`) and one manual
  smoke check. PostgreSQL-only tests are skipped on SQLite (D-30) and are not rewritten.

### Standing-rule compliance (applies to every task below)

- **D-01:**
  - No table, column, endpoint or page is removed. PostgreSQL DDL stays byte-identical,
    which BE-5.5 proves with an offline SQL diff.
  - The only exception is editing migrations 0001 and 0002 in place, named in
    **PROPOSED (D-27)**.
  - asyncpg stays installed, and aiosqlite is added.
- **D-02:** the new behaviour sits behind a setting. `DATABASE_URL` selects the dialect,
  and a PostgreSQL URL restores today's behaviour. The migration round trip is run on both
  dialects. Nothing is deleted.
- **D-03:**
  - Worktree `/home/user/HR_phase1-worktrees/sqlite-default-phase5`.
  - SQLite copies are files under the worktree's `backend/`:
    `hr_phase1_sqlite_copy.db` (dev/manual) and `hr_phase1_sqlite_test.db` (pytest).
  - The PostgreSQL check uses the existing copy `hr_phase1_mvpui_copy`.
  - The guard (BE-5.6) accepts only files whose stem ends in `_copy` or `_test`.
- **D-04:** no endpoint or permission changes. Row scoping stays in
  `principal_scope_filter`, which uses only `IN` and `IS NULL`, so it is portable as is.
  On SQLite the D-12/D-15 audit triggers are absent by user decision (D-26). Audit
  immutability rests on the insert-only `AuditService`/repository.

---

### Phase 5 — SQLite as the default local database (PostgreSQL still supported)

Goal: the backend, migrations and test suite run on a local SQLite file by default.
Switching `DATABASE_URL` back to a PostgreSQL copy gives exactly today's schema and
behaviour.
**Precondition:** none (MVP UI is complete on `master`).

- [x] BE-5.1 Isolation setup and PostgreSQL baseline (D-03). Create worktree
  `/home/user/HR_phase1-worktrees/sqlite-default-phase5` on branch
  `feature/sqlite-default-phase5` from `master` (`6e1bc77`). In the worktree, set
  `backend/.env` to the PostgreSQL copy `hr_phase1_mvpui_copy` for the baseline. Before any
  code change, capture the offline PostgreSQL SQL into the session scratchpad:
  `alembic upgrade base:head --sql > pg_upgrade_before.sql` and
  `alembic downgrade head:base --sql > pg_downgrade_before.sql`. BE-5.5 diffs against
  these files.
  Done-when: the report shows `git worktree list` with the Phase 5 path, `alembic current` on `hr_phase1_mvpui_copy` showing `0002_requisitions (head)`, and the two baseline files with their line counts. Amended 2026-10-22 (user scope cut, D-18): worktree only; the PostgreSQL `alembic current` and the offline-SQL baseline files were not captured (deferred, see below).
- [x] BE-5.2 Driver and locks (D-17). Add `aiosqlite>=0.20,<1` to `dependencies` in
  `backend/pyproject.toml`, keeping `asyncpg`. Regenerate `backend/requirements.lock` and
  `backend/requirements-dev.lock` with the `pip-compile` commands in the pyproject header,
  then reinstall the worktree `.venv` from `requirements-dev.lock`.
  Done-when: Grep finds `aiosqlite==` and `asyncpg==` in both lock files, and `python -c "import aiosqlite, asyncpg"` exits 0 in the worktree venv.
- [x] BE-5.3 Engine factory and portable column types in `app/core/db.py`
  (**PROPOSED (D-28)**, **PROPOSED (D-29)**). This adds no new core file.
  - `make_engine(url, **kw)`. On PostgreSQL it is unchanged (`pool_pre_ping=True`). On
    SQLite it adds a `connect` listener that runs `PRAGMA foreign_keys=ON` and sets
    `isolation_level=None`, plus a `begin` listener that emits `BEGIN`. This is the
    SQLAlchemy pysqlite recipe, so SAVEPOINTs and transactional DDL work. It also sets a
    15 s busy timeout and registers a `sqlite3` adapter that binds `uuid.UUID` as 32-char
    hex, which matches how `sa.Uuid` stores UUIDs on SQLite, so raw `text()` binds work.
  - Portable types:
    - `JSONType` is `JSON` with a JSONB variant on PostgreSQL.
    - `StringList(n)` is `JSON` with an `ARRAY(String(n))` variant on PostgreSQL.
    - `UTCDateTime` is a `TypeDecorator` over `DateTime(timezone=True)`. It binds as
      aware UTC and returns aware UTC, attaching UTC when SQLite hands back a naive value.
    - `utc_now()` returns `datetime.now(UTC)`.
  - `get_engine()`, `alembic/env.py` (online path) and `tests/conftest.py::db_connection`
    use `make_engine`.

  Done-when: new test `test_foreign_keys_are_enforced` in `backend/tests/test_schema.py` (inserting a `requisition_snapshot` with an unknown `requisition_id` raises `IntegrityError`) passes on SQLite (`DATABASE_URL=sqlite+aiosqlite:///./hr_phase1_sqlite_test.db`) and on `hr_phase1_mvpui_copy`, and `mypy app` passes. Amended 2026-10-22 (user scope cut, D-18): the test was not written and nothing ran on PostgreSQL; ticked on `make_engine`/`UTCDateTime` present in `app/core/db.py`, used by `alembic/env.py` and `tests/conftest.py`, and `mypy app` clean.
- [x] BE-5.4 Dialect-neutral models and repository (**PROPOSED (D-28)**).
  - **Models:** `audit/models.py`, `requisitions/models.py` and `integrations/models.py`
    use `JSONType`, `StringList(c.BUSINESS_UNIT_KEY_MAX)` and `UTCDateTime`. Columns that
    had a `clock_timestamp()` server default get `default=utc_now`, and
    `scope_business_units` gets `default=list`. The PostgreSQL-only `server_default`
    texts are removed from the ORM models only. DDL comes from the migrations, so the
    database schema does not change.
  - **Repository:** `RequisitionRepository.upsert` picks
    `sqlalchemy.dialects.sqlite.insert` or `postgresql.insert` from
    `session.get_bind().dialect.name`. Both use the same `on_conflict_do_update(...)` and
    `.returning(...)`. `func.clock_timestamp()` in `upsert` and `transition` becomes a
    bound `utc_now()`. `list_stale_ids` computes
    `cutoff = utc_now() - timedelta(seconds=older_than_seconds)` in Python. The claim
    stays `UPDATE … WHERE status='created' RETURNING` (D-06, D-26).

  Done-when: Grep finds no `clock_timestamp`, `make_interval`, `gen_random_uuid` or `dialects.postgresql` under `backend/app/modules/`, and `pytest tests/test_requisition_repository.py tests/test_ingestion.py` passes on the SQLite test file.
- [x] BE-5.5 Dialect-aware migrations in place (**PROPOSED (D-27)**, D-01 exception).
  - In `0001_audit_event.py` and `0002_requisitions.py`, branch on
    `op.get_context().dialect.name`.
  - **PostgreSQL:** the emitted SQL is unchanged.
  - **SQLite:**
    - `sa.JSON()` replaces JSONB.
    - `sa.JSON()` with server default `'[]'` replaces the varchar array.
    - There is no `gen_random_uuid()` or `clock_timestamp()` server default. The app
      supplies these values (D-28).
    - The plpgsql function and the triggers are not created, and downgrade does not drop
      them.
  - Revision IDs and `down_revision` stay the same.

  Done-when: with the PostgreSQL URL, `alembic upgrade base:head --sql` and `alembic downgrade head:base --sql` give an empty `diff` against the BE-5.1 baseline files; on the SQLite copy file, `alembic upgrade head`, `downgrade -1`, `upgrade head`, `downgrade base`, `upgrade head` all exit 0 and `alembic current` shows `0002_requisitions (head)`. Amended 2026-10-22 (user scope cut, D-18): no PostgreSQL offline-SQL diff, so byte-identical PostgreSQL DDL is unverified; on SQLite only `upgrade head → downgrade base → upgrade head` was run (current `0002_requisitions (head)`), the `downgrade -1` steps were not.
- [x] BE-5.6 Copy guard, precheck, start script, env default and ignore rules
  (**PROPOSED (D-29)**).
  - **Guard:** `app/core/db_guard.py` applies the `_copy`/`_test` rule to the file stem
    (`Path(database).stem`) when the URL's backend is `sqlite`. An empty path,
    `:memory:`, or a bare `_copy.db` is refused. PostgreSQL behaviour is unchanged.
  - **Precheck:** `scripts/dev_precheck.py` gets a SQLite branch with no server
    connection. It checks that the parent directory exists and is writable, and that
    `sqlite3.sqlite_version >= 3.35` (needed for RETURNING). It prints whether the file
    already exists or "will be created by alembic upgrade head". The asyncpg ping stays
    for PostgreSQL.
  - **`backend-start.bat`:** the step-5 comment and the `.env`-missing and precheck-failure
    messages name SQLite as the default and PostgreSQL as the alternative. The step logic
    is unchanged.
  - **`backend/.env.example`:** `DATABASE_URL=sqlite+aiosqlite:///./hr_phase1_dev_copy.db`,
    with the PostgreSQL URL kept as a commented example.
  - **Root `.gitignore`:** add `*.db`, `*.db-journal`, `*.db-wal` and `*.db-shm`.

  Done-when: new test `test_sqlite_file_name_must_be_copy` in `backend/tests/test_db_guard.py` passes (accepts `hr_phase1_dev_copy.db`, refuses `hr_phase1.db` and `:memory:`); `python scripts/dev_precheck.py` with the SQLite `.env` prints `[precheck] OK`; `git check-ignore backend/hr_phase1_sqlite_copy.db` prints the path. Amended 2026-10-22 (user scope cut, D-18): the guard test was not written; ticked on the SQLite stem rule in `db_guard.py`, the precheck `OK` line on SQLite, `*.db*` rules in `.gitignore` and no `.db` file tracked.
- [x] BE-5.7 PostgreSQL-only test marker (**PROPOSED (D-30)**). Register the marker
  `pg_only` under `[tool.pytest.ini_options] markers` (the suite uses `--strict-markers`).
  `tests/conftest.py` skips `pg_only` items when the `DATABASE_URL` dialect is not
  `postgresql`, with the reason "PostgreSQL-only safeguard or SQL (D-26)". Mark the
  following tests and do not rewrite them:
  - `test_audit.py::test_audit_event_is_append_only` (trigger and TRUNCATE);
  - `test_run_scoping.py::test_claim_is_single_winner` (row lock);
  - `test_ingestion.py::test_every_transition_has_audit_event_in_same_transaction` (xmin);
  - `test_schema.py::test_screening_run_status_has_no_check_constraint` (`pg_constraint`);
  - `migrations/test_round_trip.py`, both tests (`to_regclass`, `pg_tables`);
  - `test_hr_mock_adapter.py::test_integration_attempt_recorded_without_payload`
    (`row_to_json`);
  - `test_executor.py::test_startup_recovery_redispatches_created_and_blocks_stale`
    (`now() - interval`);
  - `test_snapshot_store.py::test_tampered_payload_raises` (`jsonb_set`).

  If any other test fails on SQLite only because of PostgreSQL SQL, the engineer may mark
  it the same way and must name it in the report.
  Done-when: on the SQLite test file `pytest -ra` passes with exactly the marked tests listed as skipped; on `hr_phase1_mvpui_copy` `pytest -ra` passes with 0 skipped. Amended 2026-10-22 (user scope cut, D-18): SQLite part only (60 passed, 10 skipped); PostgreSQL pytest not run. Engineer deviation: a 10th marked test, `test_schema.py::test_requisition_unique_external_id` (asserts the PostgreSQL constraint name), so the requisition unique constraint is untested on SQLite.

- [x] **Phase 5 Done-when:** in the Phase 5 worktree, the engineers report real output for
  each item below. Amended 2026-10-22 (user scope cut, D-18): (a) met except `downgrade -1`
  (base round trip run instead); (b) not run, so PostgreSQL compatibility is unverified;
  (c) met.
  - **(a) On SQLite** (`DATABASE_URL=sqlite+aiosqlite:///./hr_phase1_sqlite_test.db`):
    `ruff check .`, `mypy app` and `pytest -ra` pass, with only `pg_only` tests skipped.
    `alembic upgrade head → downgrade -1 → upgrade head` exits 0 on
    `hr_phase1_sqlite_copy.db`.
  - **(b) On PostgreSQL** (`hr_phase1_mvpui_copy`): the full `pytest -ra` passes with 0
    skipped, the round-trip tests included. The migration round trip runs and the BE-5.5
    offline SQL diff is empty.
  - **(c) Manual smoke check:** start the backend from the worktree with
    `scripts/start-backend.sh`, using the default `.env.example` URL pointed at
    `hr_phase1_sqlite_copy.db`, `FEATURE_SCREENING_RUNS=true`, `AUTH_MODE=dev_header` and
    `HR_SYSTEM_ADAPTER=mock`. POST `/api/v1/screening-runs`
    `{"external_requisition_id":"REQ-OPEN-1"}` returns 202. GET on the `status_url`
    returns `status: role_brief_draft`, with timestamps carrying a UTC offset.
  - The user checks `backend-start.bat` once on Windows (Q-20).

**Verified 2026-10-22 (MVP-light, user scope cut; solution-architect).** Feature complete.
Merged at `caad1c8` from worktree `/home/user/HR_phase1-worktrees/sqlite-default-phase5`.
Mid-build the user cut scope to "no unnecessary testing" (D-18); the cut items are listed
under "Deferred (user scope cut)" below and do not block the ticks.
- Orchestrator run on SQLite in the worktree: `ruff check .` "All checks passed!";
  `mypy app` "Success: no issues found in 38 source files"; `pytest` "60 passed, 10 skipped
  in 1.23s"; no `.db` or `.env` file tracked.
- Engineer report: `mypy scripts/dev_precheck.py` clean; `alembic upgrade head → downgrade
  base → upgrade head` on `hr_phase1_sqlite_copy.db`, current `0002_requisitions (head)`;
  lock files add only `aiosqlite==0.22.1` (`asyncpg` kept); precheck `OK` on SQLite; smoke
  POST `REQ-OPEN-1` → 202, GET → `role_brief_draft` with timestamps ending in `Z`.
- Confirmed by Grep: `make_engine`, `JSONType`, `StringList`, `UTCDateTime`, `utc_now` in
  `backend/app/core/db.py`, with `make_engine` used by `alembic/env.py` and
  `tests/conftest.py`; SQLite stem rule in `backend/app/core/db_guard.py`; SQLite branch
  (`sqlite_version`, "will be created by alembic upgrade head") in
  `backend/scripts/dev_precheck.py`; SQLite default and commented PostgreSQL URL in
  `backend/.env.example`; `pg_only` marker in `backend/pyproject.toml` and skip hook in
  `backend/tests/conftest.py`, applied to 10 tests; dialect branch in both migrations;
  dialect switch in `requisitions/repository.py`; no `clock_timestamp`, `make_interval`,
  `gen_random_uuid` or `dialects.postgresql` under `backend/app/modules/`;
  `aiosqlite==0.22.1` and `asyncpg==0.32.0` in both lock files; `*.db`, `*.db-journal`,
  `*.db-wal`, `*.db-shm` in `.gitignore`. Grep confirms `test_foreign_keys_are_enforced`
  and `test_sqlite_file_name_must_be_copy` do not exist (user cut).
- Open: the user's Windows check of `backend-start.bat` (Q-20).

**Reversibility:**
- Set `DATABASE_URL` back to a `postgresql+asyncpg://…_copy` URL. No code change is
  needed. Caveat (user scope cut): the PostgreSQL path was not re-verified in Phase 5; run
  the deferred PostgreSQL checks below before relying on it. The PostgreSQL DDL is byte-identical (BE-5.5 diff), so existing PostgreSQL copies
  at `0002_requisitions` need no migration action, and the full suite runs there unskipped.
- Reverting the branch restores the PostgreSQL-only code. The `.env.example` default goes
  back to the PostgreSQL placeholder. The added lock entries and `.gitignore` lines are
  harmless if left.
- SQLite copy files stay on disk, gitignored, and are never deleted by the plan.
- What remains afterwards on SQLite: no DB-level audit immutability and no row-lock claim
  (D-26).

**Deferred from Phase 5:**
- SQLite triggers for audit append-only (`BEFORE UPDATE/DELETE … RAISE(ABORT)`). The user
  decided app-level only (D-26). See Q-18.
- Portable rewrites of the `pg_only` tests (D-18).
- CI running the suite on both dialects.
- WAL mode and multi-process access to the SQLite file.
- A data copy tool from SQLite to PostgreSQL. Pilot starts on a fresh PostgreSQL database.
- SQLite in staging, pilot or production. Not supported.

**Deferred (user scope cut, 2026-10-22, D-18) — revisit at pre-pilot hardening, with Q-21:**
- New test `test_schema.py::test_foreign_keys_are_enforced` (BE-5.3), not written.
- New test `test_db_guard.py::test_sqlite_file_name_must_be_copy` (BE-5.6), not written.
- PostgreSQL verification: the offline-SQL baseline and empty diff (BE-5.1/BE-5.5), the
  full `pytest -ra` on `hr_phase1_mvpui_copy` with 0 skipped, and the PostgreSQL migration
  round trip (Phase Done-when (b), BE-5.7). PostgreSQL compatibility is unverified until
  this runs.
- The longer SQLite migration sequence with `downgrade -1` (BE-5.5, Phase Done-when (a)).
  The base round trip was run.
- A portable SQLite check for the requisition unique constraint. The 10th `pg_only` test
  (`test_schema.py::test_requisition_unique_external_id`, engineer deviation) leaves it
  untested on SQLite.

### Open questions for approval (SQLite default)

Numbered from Q-17 so they do not collide with Q-1…Q-16.

**Resolved 2026-10-22:** the user approved all defaults (Q-17…Q-21).

- **Q-17** Approve or amend D-27…D-30. Defaults: edit 0001/0002 in place, use the app
  clock on both dialects, use the connection setup and guard as written, and use the
  `pg_only` marker.
- **Q-18** Confirm there should be no SQLite audit trigger. Adding one would be about six
  lines in 0001's SQLite branch and would give DB-level immutability on SQLite too. The
  default follows your decision 2: app level only.
- **Q-19** pytest on SQLite uses a separate `hr_phase1_sqlite_test.db`, set through the
  `DATABASE_URL` environment variable, so tests never share the file the running backend
  uses. Should `conftest.py` switch to that file automatically when `.env` points at a
  SQLite `_copy` file? The default is no: tests use an explicit env var, as today.
- **Q-20** Will you check `backend-start.bat` once on Windows after Phase 5? The Linux
  container cannot run it. This is like Q-12.
- **Q-21** Should every later backend phase also run `pytest` on a PostgreSQL copy, so the
  two dialects do not drift? The default is yes while `hr_phase1_mvpui_copy` exists. It
  becomes mandatory at the D-18 revisit before pilot.

---

## Feature: Role Brief (AI) — COMPLETE

- **Verified 2026-10-22 (MVP-light, D-18).** Phases 6 (backend) and 7 (frontend) built,
  verified and merged to the session branch (Phase 7 at `32a2c14`). Frontend evidence
  (Grep): `src/api/role-briefs.ts` (`getRoleBrief`, `approveRoleBrief`),
  `src/api/messages.ts` (role-brief labels + `role_brief:approve` 403), `src/features.ts`
  (`isRoleBriefEnabled`), `src/dev-auth/presets.ts` (`dev-approver-bu-1`,
  `role_brief:approve`), `src/app/screening-runs/[runId]/RoleBriefPanel.tsx`, and
  0 `dangerouslySetInnerHTML` under `frontend/src`. Gates: `npm run build/typecheck/lint`
  exit 0; backend ruff clean, mypy clean (50 files), pytest 67 passed / 9 skipped (SQLite).
  Browser walkthrough (mock AI) passed all four steps. Known MVP deviations: the approve
  button renders for any principal in `awaiting_role_approval` (backend enforces
  `role_brief:approve`, D-04); the Role card omits responsibilities/capabilities; no separate
  flag-off walkthrough (D-24 path unchanged). **Still pending with the user:** BE-6.8
  real-Groq smoke test.
- **Kickoff:** `docs/prompts/kickoffs/2026-10-22-role-brief.md`
- **Plan status:** APPROVED by the user, 2026-10-22 — all defaults accepted (Q-22…Q-28); D-32…D-39 Accepted. D-31 records the user's decisions
  (Accepted). D-32…D-39 are "Proposed — awaiting approval", and the tasks below use their
  defaults. If approval changes a default, I amend the affected tasks before the build.
- **Plan author:** solution-architect, 2026-10-22
- **Specs and decisions used:** System Design §5; Tech Arch §2 (provider-neutral model
  gateway), §5.1 (runtime sequence, example output, design controls), §6.1, §6.2, §8, §9 (AI
  governance, prompt-injection); Data Model §4.4, §7.1, §8. D-01…D-04, D-06, D-08, D-09,
  D-11, D-12, D-13, D-18, D-20…D-26, D-28, D-29, D-30.
- **Starting point:** `master` = `1f4406a` (verified by Read/Grep):
  - `RunStatus` in `backend/app/modules/requisitions/constants.py` already defines
    `awaiting_role_approval` and `role_configuration`. Runs stop at `role_brief_draft`.
  - `screening_run.role_brief_version_id` exists (nullable `Uuid`, no FK) in
    `requisitions/models.py`.
  - `ScreeningRunRepository.transition` (conditional on `expected_status`) has no
    `role_brief_version_id` argument yet. `PHASE_1_BY_STATUS` maps only
    `created/ingesting_requisition/role_brief_draft/blocked`.
  - `build_ingestion_handler` / `build_run_executor` in `requisitions/service.py` are wired
    in `app/main.py` only when `FEATURE_SCREENING_RUNS=true`.
  - The adapter pattern is `integrations/adapters/hr_system/{base.py, mock.py, fixtures/}`
    plus `HRSystemService` in `integrations/service.py`, which writes one
    `integration_attempt` per call and never stores bodies.
  - `httpx` is a dev-only dependency in `backend/pyproject.toml`.
  - Migrations end at `0002_requisitions`. `scripts/export_openapi.py` pins
    `FEATURE_SCREENING_RUNS=true`, `HR_SYSTEM_ADAPTER=mock`.
  - Frontend: `RunStatusView.tsx` stops polling at `role_brief_draft`/`blocked` (D-24).
    `src/dev-auth/presets.ts` has four presets with no `role_brief:*` permission.
- **Task ID scheme:** continues the global phase sequence (Phases 0–5 are used). This
  feature is **Phase 6** (backend, BE-6.x) and **Phase 7** (frontend, FE-7.x).
- **Testing level (D-18, user wants minimal testing):**
  - Backend: `ruff check .`, `mypy app`, `pytest` on SQLite (D-26) and the Alembic round
    trip `upgrade head → downgrade -1 → upgrade head`. New tests: five in total, all using
    the mock AI provider. Tests never call Groq.
  - Frontend: `npm run build`, `npm run lint`, `npm run typecheck`. No test runner.
  - One manual real-Groq smoke (BE-6.8, only if `GROQ_API_KEY` is set) and one browser
    walkthrough (Phase 7 Done-when).
  - No PostgreSQL runs (deferred, D-30/Q-21). Code stays dialect-neutral (D-28):
    `JSONType`, `UTCDateTime`, app-side `uuid4`/`utc_now` defaults, no dialect imports
    under `app/modules/`.

### Standing-rule compliance (applies to every task below)

- **D-01:** one new table (`role_brief_version`) in a new migration `0003_role_briefs`. Every
  other change is additive: new enum members, a new optional repository argument, a new
  nullable response field, new routes, new settings, new fixtures, new UI components. No
  existing route, column, page or test is removed or changed in meaning.
- **D-02:** `0003_role_briefs` has a tested downgrade (Alembic CLI round trip). New
  behaviour sits behind `FEATURE_ROLE_BRIEF` (backend, default `false`) and
  `NEXT_PUBLIC_FEATURE_ROLE_BRIEF` (frontend, default `false`). With both off, runs stop at
  `role_brief_draft` exactly as today. Briefs are never deleted. A failed generation blocks
  the run (a status, not a deletion), and approval changes status, never content.
- **D-03:** worktrees `/home/user/HR_phase1-worktrees/role-brief-phase6` and
  `…/role-brief-phase7`. SQLite copies under each worktree's `backend/`:
  `hr_phase1_rolebrief_copy.db` (manual) and `hr_phase1_sqlite_test.db` (pytest). The D-29
  stem guard refuses anything else.
- **D-04:** `GET /screening-runs/{run_id}/role-brief` needs `screening_run:read`.
  `POST /screening-runs/{run_id}/approve-role-brief` needs `role_brief:approve` (D-34). Both
  load the run through `ScreeningRunRepository.get_for_principal` (D-09 scope from the
  principal), so a missing or out-of-scope run returns 404. `create_app`'s route check
  (D-15) covers the new routes.

### Status flow added by this feature (Data Model §7.1 subset)

```
… ingesting_requisition ──eligible──▶ role_brief_draft ──AI ok + schema + citations valid──▶ awaiting_role_approval ──approve (role_brief:approve)──▶ role_configuration (stops here)
                                             │
                                             ├──provider down / timeout / auth / rate limit──▶ blocked (role_brief_ai_unavailable)
                                             └──bad JSON / schema / unverified citation─────▶ blocked (role_brief_output_invalid)
```

---

### Phase 6 — Backend: role_briefs module, AI gateway (Groq + mock), approve endpoint

Goal: with `FEATURE_ROLE_BRIEF=true`, a run that reaches `role_brief_draft` gets an
AI-generated, schema-validated and citation-checked `role_brief_version` and moves to
`awaiting_role_approval`. A permitted user can read it and approve it, which moves the run
to `role_configuration`. AI failure blocks the run with a reason and stores no brief.
**Precondition:** D-32…D-39 approved (or amended).

- [x] BE-6.1 Isolation setup (D-03). Create worktree
  `/home/user/HR_phase1-worktrees/role-brief-phase6` on branch `feature/role-brief-phase6`
  from `master` (`1f4406a`). In its `backend/.env` set
  `DATABASE_URL=sqlite+aiosqlite:///./hr_phase1_rolebrief_copy.db` and run `alembic upgrade
  head`. `backend/.env` is gitignored, and `GROQ_API_KEY` is only ever put there or in the
  shell environment (D-31).
  Done-when: the report shows `git worktree list` with the Phase 6 path and `alembic current` on `hr_phase1_rolebrief_copy.db` showing `0002_requisitions (head)`.
- [x] BE-6.2 Settings, dependency and env example (D-31, D-32). In
  `backend/app/core/settings.py` add:
  - `FEATURE_ROLE_BRIEF: bool = False`;
  - `AI_PROVIDER: str | None = None` (`mock` | `groq`);
  - `AI_MODEL: str = "openai/gpt-oss-120b"` (D-37);
  - `AI_TIMEOUT_SECONDS: float` (default 60, `gt=0`, `le=300`);
  - `GROQ_API_KEY: SecretStr | None = None` (pydantic `SecretStr`, so it never appears in
    `repr`, logs or errors);
  - `GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"`.

  `unsafe_configuration_reasons` adds these refusals:
  - `FEATURE_ROLE_BRIEF=true` without `FEATURE_SCREENING_RUNS=true`, or without
    `AI_PROVIDER`;
  - `AI_PROVIDER=groq` with an empty `GROQ_API_KEY`;
  - `AI_PROVIDER=mock` when `ENVIRONMENT=production`.

  Move `httpx` from the dev extra to `dependencies` in `backend/pyproject.toml` (the Groq
  adapter uses it; there is no Groq SDK). Regenerate both lock files (D-17). In
  `backend/.env.example`, add commented lines with names only: `# FEATURE_ROLE_BRIEF=false`,
  `# AI_PROVIDER=`, `# AI_MODEL=openai/gpt-oss-120b`, `# AI_TIMEOUT_SECONDS=60` and
  `# GROQ_API_KEY=` (no value, with the note "set in backend/.env or the shell; never
  commit").
  Done-when: new test `test_settings.py::test_role_brief_requires_ai_provider_and_key` passes (flag without provider, and `groq` without key, both raise `UnsafeConfigurationError`), and Grep finds `httpx==` in `backend/requirements.lock` and `GROQ_API_KEY=` with no value in `backend/.env.example`.
- [x] BE-6.3 AI model gateway in `integrations` (D-31, D-35, D-39). Add
  `backend/app/modules/integrations/adapters/ai_model/`:
  - `base.py`: an `AIModelAdapter` protocol (`provider_key`,
    `async complete_json(request: AIRequest) -> AIResponse`); frozen dataclasses
    `AIRequest` (`system_prompt`, `user_content`, `json_schema`, `model`,
    `max_output_tokens`, `routing_key` — non-sensitive metadata used only by the mock and
    never sent to a provider) and `AIResponse` (`content` text, `model` as reported by the
    provider, `http_status`); typed errors `AIUnavailable` (error codes `timeout`,
    `unavailable`, `auth_failed`, `rate_limited`) and `AIOutputInvalid` (`invalid_json`,
    `refused`).
  - `groq.py`: `GroqAdapter` POSTs `{GROQ_BASE_URL}/chat/completions` with httpx,
    `Authorization: Bearer <key>` taken from `SecretStr.get_secret_value()` only at call
    time. It sends the two messages, `temperature` 0, a JSON-schema `response_format` and
    no tools. It is a single attempt with no retries (D-06). It maps HTTP 401/403, 429, 5xx
    and timeouts to `AIUnavailable` codes. It never logs or puts into exception messages
    the key, headers, prompt or response bodies.
  - `mock.py` plus `fixtures/`: `MockAIModelAdapter` returns
    `fixtures/role_brief_<routing_key>.json` as the content. `REQ-OPEN-1` gets a valid brief
    whose quotes match that HR fixture. `REQ-AI-INVALID-1` gets a brief with a quote that is
    not in its source. `REQ-AI-UNAVAILABLE-1` raises `AIUnavailable("unavailable")`. Any
    other key raises `AIUnavailable`. The ID is a dict key only, never a path (as in the HR
    mock).
  - Add two HR fixtures, `REQ-AI-INVALID-1.json` and `REQ-AI-UNAVAILABLE-1.json` (open,
    complete, `bu-1`), under `adapters/hr_system/fixtures/`.
  - `integrations/service.py`: `build_ai_model_adapter(settings)` (unset or unknown
    provider fails closed; `mock` refused in production), and
    `AIGatewayService.generate_structured(request, output_model, *, screening_run_id,
    correlation_id, operation)`. It applies `asyncio.timeout(AI_TIMEOUT_SECONDS)`, parses
    JSON, validates it with the given pydantic model (an error lists field locations only),
    and writes one `integration_attempt` (`integration_name="ai_model"`, operation
    `role_brief.generate`, outcome, `error_code`, `http_status`; no bodies) in the caller's
    unit of work. Constants go in `integrations/constants.py`.
  Done-when: `mypy app` passes and BE-6.5's `test_generation_creates_brief_and_awaits_approval` asserts exactly one `integration_attempt` with `integration_name == "ai_model"` and outcome `success` for the run.
- [x] BE-6.4 Migration `0003_role_briefs` and model (D-37, D-28). Add
  `backend/alembic/versions/0003_role_briefs.py` (down_revision `0002_requisitions`),
  dialect-aware like 0002: `JSON` on SQLite, JSONB on PostgreSQL, no server-side UUID or
  clock defaults on SQLite. It creates `role_brief_version` with the Data Model §4.4
  columns:
  - `id`, `requisition_id` (FK `requisition.id`), `version_number`, `status`,
    `structured_role_data`, `explicit_source_facts`, `ai_inferences`, `ambiguities`,
    `source_snapshot_id` (FK `requisition_snapshot.id`), `schema_version`, `created_by`,
    `approved_by`, `approved_at`, `created_at`;
  - plus the D-37 additions: `screening_run_id` (FK `screening_run.id`, not null),
    `source_payload_hash`, `prompt_version`, `model_provider`, `model_name`.

  It adds unique `(requisition_id, version_number)` and an index on `screening_run_id`.
  There is no FK on `screening_run.role_brief_version_id` (D-37). `downgrade()` drops only
  the index and the table. Add `RoleBriefVersion` in `role_briefs/models.py`, using
  `JSONType`, `UTCDateTime`, `default=uuid.uuid4` and `default=utc_now`.
  Done-when: on `hr_phase1_rolebrief_copy.db`, `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head` all exit 0 and `alembic current` shows `0003_role_briefs (head)` (output in the report).
- [x] BE-6.5 `role_briefs` module and generation service (D-32, D-33, D-35, D-36, D-37). The
  standard seven files go in `backend/app/modules/role_briefs/`.
  - `constants.py`: `RoleBriefStatus` (`draft`, `awaiting_review`, `approved`,
    `superseded`), `ROLE_BRIEF_SCHEMA_VERSION="1"`, `ROLE_BRIEF_PROMPT_VERSION="role_brief.v1"`,
    the fixed system prompt text (D-35), `PERMISSION_ROLE_BRIEF_APPROVE="role_brief:approve"`,
    `GENERATOR_ACTOR_ID="role_briefs.generator"`, and the column limits.
  - `schemas.py`: `RoleBriefOutputV1` (extra forbidden) with these fields:
    - `role_title`, `role_purpose`, `responsibilities`, `required_capabilities`,
      `preferred_capabilities`, `seniority`, `location_constraints`,
      `employment_constraints`. Each is a `BriefItem{text, basis: "source_fact" |
      "ai_inference", source_refs: [{path, quote}]}`.
    - `explicit_source_facts` `[{statement, source_refs}]`.
    - `ai_inferences` `[{statement, rationale, source_refs}]`.
    - `ambiguities` `[{topic, description, severity: "material" | "minor",
      suggested_question}]`.

    It also holds `RoleBriefResponse` and `ApproveRoleBriefRequest`. The JSON schema sent to
    the provider is `RoleBriefOutputV1.model_json_schema()`.
  - `repository.py`: `RoleBriefRepository` with `add`, `get`, `next_version_number(
    requisition_id)`, and `approve(id, approved_by)`. `approve` is a conditional `UPDATE …
    WHERE status='awaiting_review' RETURNING` and is the only update path (immutability,
    D-37).
  - `service.py`, `RoleBriefService.generate(run_id)`:
    1. Load the run with `get_for_workflow`. It must be in `role_brief_draft` with no
       `role_brief_version_id`, otherwise it is a no-op.
    2. Load the payload with `SnapshotService.load_payload` (hash-verified).
    3. Call `AIGatewayService` outside any open transaction (D-32), with `routing_key =
       external_requisition_id`.
    4. Run the deterministic checks: D-36 citation verification, and the rule that every
       `required_capabilities` and `responsibilities` item is a `source_fact` with at least
       one verified ref ("do not invent mandatory requirements", Tech Arch §5.1).
    5. In one unit of work, insert the version (`awaiting_review`, `created_by =
       "ai_model:<provider>/<model>"`) and run the conditional `transition(role_brief_draft
       → awaiting_role_approval, role_brief_version_id=…)`. The audit events
       `RoleBriefCreated` and `RunStatusChanged` (actor `system`/`role_briefs.generator`,
       the run's correlation_id, details limited to IDs, versions, model name and item
       counts) go in the same unit (D-12).

    On `AIUnavailable` or `AIOutputInvalid`, the run is blocked per D-33 in one unit of
    work with its audit event, and no version row is stored.
  - Additive changes in `requisitions`:
    - `CompletionReason` gains `ROLE_BRIEF_AI_UNAVAILABLE` and `ROLE_BRIEF_OUTPUT_INVALID`.
    - `ScreeningRunRepository.transition` gains an optional `role_brief_version_id`.
    - `PHASE_1_BY_STATUS` gains the D-38 entries.
    - `ScreeningRunStatusResponse` gains nullable `role_brief_version_id`.
    - `events.py` in `role_briefs` names `RoleBriefCreated` and `RoleBriefApproved`.
  Done-when: new tests `tests/test_role_briefs.py::test_generation_creates_brief_and_awaits_approval` (mock provider, `REQ-OPEN-1`: run is `awaiting_role_approval`, `role_brief_version_id` set, version `awaiting_review` with `model_name`, `prompt_version`, `schema_version`, `source_payload_hash` recorded, `RoleBriefCreated` audited) and `tests/test_role_briefs.py::test_invalid_ai_output_blocks_run` (`REQ-AI-INVALID-1`: run `blocked/role_brief_output_invalid` with `status_details.error_code == "citation_unverified"`, no `role_brief_version` row) pass on SQLite.
- [x] BE-6.6 Executor wiring and HTTP routes (D-32, D-34, D-38).
  - `RoleBriefService` gets a builder `build_role_brief_handler(settings, gateway_adapter,
    session_scope)` in `role_briefs/service.py`. In `app/main.py`, when
    `FEATURE_ROLE_BRIEF=true`, the run handler becomes "ingest, then (new session)
    generate if the run is in `role_brief_draft`" inside the same `RunExecutor` dispatch.
    `requisitions/service.py` is unchanged apart from the BE-6.5 additions.
  - Add `role_briefs/router.py`, mounted under `/api/v1` only when
    `FEATURE_ROLE_BRIEF=true`:
    - `GET /screening-runs/{run_id}/role-brief`. Permission `screening_run:read`. Returns
      `RoleBriefResponse`: the brief sections, `version_number`, `status`, `schema_version`,
      `prompt_version`, `model_provider`, `model_name`, `source_snapshot_id`,
      `source_payload_hash`, `created_at`, `approved_by` and `approved_at`. It never returns
      the raw snapshot payload. Returns 404 if the run is missing, out of scope or has no
      brief.
    - `POST /screening-runs/{run_id}/approve-role-brief`. Permission `role_brief:approve`.
      Body `{"role_brief_version_id": uuid}`, extra fields forbidden. In one unit of work it
      runs `RoleBriefRepository.approve` (`approved_by` = principal ID, `approved_at` =
      `utc_now()`), the conditional run transition `awaiting_role_approval →
      role_configuration`, and the audit events `RoleBriefApproved` (actor `user`, details
      include `material_ambiguities` count, D-38) and `RunStatusChanged`. Returns 200
      `RoleBriefResponse`. Returns 409 if the run is not in `awaiting_role_approval` or the
      ID is not the run's current version, and 404 if the run is missing or out of scope.
    - The router calls only `RoleBriefService`. The service re-checks the permission as
      defence in depth (as `ScreeningRunService` does).
  Done-when: new tests `tests/test_api_role_briefs.py::test_brief_generated_and_approved_end_to_end` (`RUN_EXECUTOR=inline`, `AI_PROVIDER=mock`: POST `REQ-OPEN-1` → GET status `awaiting_role_approval` with phase_1 `awaiting_approval` → GET role-brief 200 → approve 200 → GET status `role_configuration` with phase_1 `completed`) and `tests/test_api_role_briefs.py::test_approve_without_permission_403` pass.
- [x] BE-6.7 OpenAPI re-export (D-23). In `backend/scripts/export_openapi.py`, add
  `FEATURE_ROLE_BRIEF=true` and `AI_PROVIDER=mock` to `EXPORT_ENVIRONMENT` and to the
  `Settings(...)` call. No key is needed or read. Run it and commit `backend/openapi.json`.
  Done-when: Grep shows `/api/v1/screening-runs/{run_id}/role-brief` and `/api/v1/screening-runs/{run_id}/approve-role-brief` under `paths` in `backend/openapi.json`, and `role_brief_version_id` in the `ScreeningRunStatusResponse` schema.
- [ ] BE-6.8 Manual real-Groq smoke (D-31). Run only if `GROQ_API_KEY` is set in the
  environment or in the worktree's gitignored `backend/.env`. Start
  `scripts/start-backend.sh` from the worktree with `FEATURE_SCREENING_RUNS=true`,
  `FEATURE_ROLE_BRIEF=true`, `AUTH_MODE=dev_header`, `HR_SYSTEM_ADAPTER=mock`,
  `AI_PROVIDER=groq`, and the default `AI_MODEL`. POST `REQ-OPEN-1`, poll GET, then GET
  role-brief. If the key is not set, the report says "not run: no GROQ_API_KEY", the task
  stays unticked and is listed as deferred, and it does not block Phase 7.
  Done-when: the report shows the run reaching `awaiting_role_approval` (or, if the model's output fails validation, `blocked/role_brief_output_invalid` with its `error_code`, reported as a finding), the brief's `model_name`, and `grep -c` of the key value over the backend console log and `git diff`/`git status` output returning 0.
  Note: Not run 2026-10-22 — the session's permission checks blocked passing the API key on the command line (credential-leak guard). Pending: user adds GROQ_API_KEY to their laptop backend/.env (or the cloud environment settings) and runs it. Per this task, BE-6.8 does not block Phase 7.

- [x] **Phase 6 Done-when:** in the Phase 6 worktree on SQLite
  (`DATABASE_URL=sqlite+aiosqlite:///./hr_phase1_sqlite_test.db` for pytest), the engineer
  reports real output: `ruff check .` and `mypy app` clean; `pytest -ra` passes, with only
  the existing `pg_only` tests skipped; and the BE-6.4 round trip. BE-6.8 has either been
  run or been recorded as "not run: no key". `git status` shows no `.env` or `.db` file
  tracked.
  Caveat: ticked with BE-6.8 recorded as not run (see its note); it stays open.

**Verified 2026-10-22 (MVP-light, D-18).** Merged to `master` at `324bcb4`.
- Light Grep confirmed that the five named tests exist:
  - `tests/test_settings.py::test_role_brief_requires_ai_provider_and_key`;
  - `tests/test_role_briefs.py::test_generation_creates_brief_and_awaits_approval` and `::test_invalid_ai_output_blocks_run`;
  - `tests/test_api_role_briefs.py::test_brief_generated_and_approved_end_to_end` and `::test_approve_without_permission_403`.
- Grep also confirmed `alembic/versions/0003_role_briefs.py`, `app/modules/role_briefs/` (seven files), `app/modules/integrations/adapters/ai_model/{base,mock,groq}.py`, and the `/role-brief` and `/approve-role-brief` paths in `backend/openapi.json`.
- Orchestrator run in the worktree on SQLite:
  - `ruff check .` printed "All checks passed!";
  - `mypy app` printed "Success: no issues found in 50 source files";
  - `pytest` printed "65 passed, 10 skipped in 1.68s" (the 10 skips are `pg_only`);
  - no `.db` or `.env` file is tracked;
  - `.env.example` line 29 reads `# GROQ_API_KEY=` with no value.
- Engineer report:
  - `alembic upgrade` → `downgrade -1` → `upgrade` ran clean, and `alembic current` shows `0003_role_briefs (head)`;
  - the OpenAPI export wrote 5 paths;
  - mock smoke: POST `REQ-OPEN-1` 202 → GET `awaiting_role_approval` with phase_1 `awaiting_approval` → GET role-brief 200 (mock provider, prompt `role_brief.v1`, schema 1, citations present) → approve as recruiter 403 → approve as approver-1 200 `approved` → GET `role_configuration` with phase_1 `completed`.
- Deviations from the plan (accepted for MVP-light):
  - the pytest DB name is `hr_phase1_rolebrief_test.db`, not `hr_phase1_sqlite_test.db`;
  - `RoleBriefResponse` adds `screening_run_id`, `requisition_id` and `created_by`;
  - `seniority` is a single `BriefItem` and the constraint fields are lists (all required, strict-ready);
  - on citation failures the `integration_attempt` row stays `success`, and the failure is recorded on the run and in the audit log;
  - the success and approval audit reason codes are plain strings;
  - `<` and `>` are escaped in the prompt's JSON block, so citation checks may fail if the model copies the escaped form;
  - a lost generation race leaves no attempt row.
- Not verified by me: the test output and the round trip were not re-run by the architect (no shell). They rest on the orchestrator's and the engineer's reported output.

**Reversibility:**
- `FEATURE_ROLE_BRIEF=false` (the default) mounts no role-brief routes, builds no AI adapter
  and does not chain generation. Runs stop at `role_brief_draft` exactly as before. The only
  visible API change is the always-present, nullable `role_brief_version_id` field on the
  run status response (additive).
- `alembic downgrade 0002_requisitions` drops `role_brief_version`. What remains afterwards:
  - runs already in `awaiting_role_approval` or `role_configuration` keep those statuses;
  - their `role_brief_version_id` values dangle, since there is no FK (D-37);
  - `integration_attempt` and audit rows stay (append-only).

  Once real approved briefs exist, downgrading `0003` needs a new decision, because it would
  destroy approval records.
- Reverting the branch removes the module. The added HR fixtures and `.env.example` lines
  are harmless.

**Deferred from Phase 6:**
- Retry endpoint and re-generation of a brief, plus editing a brief (kickoff out of scope;
  D-33: retry = start a new run).
- Startup recovery of runs left in `role_brief_draft` by a restart mid-call (Q-24).
- Clarification-question workflow with HR and the `awaiting_role_review` state (Q-27).
- Re-ingestion and re-generation when the source version changes (Tech Arch §5.1).
- Multiple AI providers, provider fallback and model routing (kickoff out of scope; the
  gateway is the seam).
- Retries with backoff for AI calls (D-06 single attempt).
- Tests not written under D-18: Groq adapter HTTP mapping (httpx `MockTransport`), the
  `role_brief_ai_unavailable` path, 409 on double approve, out-of-scope 404 on the new
  routes, a key-never-logged test, and the `FEATURE_ROLE_BRIEF=false` → 404 route test.
- FK `screening_run.role_brief_version_id → role_brief_version.id` (D-37).
- PostgreSQL run of the suite and of the round trip (D-30/Q-21, deferred by the user).
- AI evaluation for quality, disparate errors and job-related validity (Tech Arch §9,
  §13) before pilot.

---

### Phase 7 — Frontend: role brief view and approve on the run status page

Goal: on `/screening-runs/[runId]` a user sees the brief, with facts, AI inferences and
ambiguities clearly separated and each traceable to a snapshot path and quote. A user with
`role_brief:approve` can approve it.
**Precondition:** Phase 6 verified, ticked and merged to `master`.

- [x] FE-7.1 Isolation setup (D-03). Create worktree
  `/home/user/HR_phase1-worktrees/role-brief-phase7` on branch `feature/role-brief-phase7`
  from `master` with Phase 6 merged. Migrate `backend/hr_phase1_rolebrief_copy.db` in the
  worktree to head.
  Done-when: the report shows `git worktree list` with the Phase 7 path and `alembic current` showing `0003_role_briefs (head)`.
- [x] FE-7.2 API functions and messages. Run `npm run gen:api`. Add
  `frontend/src/api/role-briefs.ts` with `getRoleBrief(runId)` and
  `approveRoleBrief(runId, roleBriefVersionId)`, typed only from `src/api/schema.d.ts`. In
  `src/api/messages.ts` add:
  - labels for `role_brief_ai_unavailable` ("The AI service was unavailable. Start a new
    run to try again.") and `role_brief_output_invalid` ("The AI output failed validation;
    no brief was stored.");
  - a 403 message on approve naming `role_brief:approve`;
  - a 409 message on approve ("This brief can no longer be approved. Refresh.");
  - a 404 message on the brief GET ("No role brief yet.").
  Done-when: `npm run typecheck` passes and Grep finds no hand-written `(type|interface) .*RoleBrief` under `frontend/src` outside `src/api/schema.d.ts`.
- [x] FE-7.3 UI flag and dev preset (D-34, D-38, D-21). Add `isRoleBriefEnabled()`
  (`NEXT_PUBLIC_FEATURE_ROLE_BRIEF`, default `false`) to `frontend/src/features.ts`, and
  `NEXT_PUBLIC_FEATURE_ROLE_BRIEF=false` to `frontend/.env.example`. In
  `frontend/src/dev-auth/presets.ts` add the preset "Approver bu-1" (`dev-approver-bu-1`,
  permissions `screening_run:read, role_brief:approve`, `bu-1`). The existing four presets
  are unchanged.
  Done-when: `npm run build`, `npm run lint` and `npm run typecheck` pass and Grep finds `role_brief:approve` in `frontend/src/dev-auth/presets.ts`.
- [x] FE-7.4 Role brief panel and approve on the run status page (D-38, D-20).
  - **Polling.** In `RunStatusView.tsx`, when `isRoleBriefEnabled()`, the stopping
    statuses become `awaiting_role_approval`, `role_configuration` and `blocked`, and
    `role_brief_draft` keeps polling. When the flag is off, D-24 is unchanged. Status tones:
    `awaiting_role_approval` warning, `role_configuration` success.
  - **Panel.** When the run has `role_brief_version_id`, a local component
    `frontend/src/app/screening-runs/[runId]/RoleBriefPanel.tsx` (page-local, not a new
    shared `ui/` component) fetches the brief once and renders it with the existing `Card`,
    `KeyValueList`, `StatusBadge`, `Alert` and `Button`:
    - "Role" (title, purpose, seniority, constraints);
    - "From the requisition (facts)": each item with its `path` and quoted text;
    - "AI inferences": labelled "AI suggestion", with rationale and refs;
    - "Ambiguities": severity badge and suggested question;
    - "Provenance": version, status, model, prompt and schema version, snapshot ID and
      hash, approved by and at.
  - **Approve.** An "Approve role brief" button shows only while the run is in
    `awaiting_role_approval`. It is disabled while submitting and, if material ambiguities
    exist, labelled "Approve (accepts listed ambiguities)". It POSTs with the shown version
    ID, then refreshes the run and the brief. Errors appear in an `Alert` using the FE-7.2
    messages.
  - All text is rendered as escaped data.
  Done-when: `npm run build`, `npm run lint` and `npm run typecheck` pass and Grep finds no `dangerouslySetInnerHTML` under `frontend/src`.

- [x] **Phase 7 Done-when:** in the Phase 7 worktree, `npm run build`, `npm run lint` and
  `npm run typecheck` pass, and backend `ruff check .`, `mypy app` and `pytest` pass. One
  browser walkthrough (screenshots in the report) is run with the backend from
  `scripts/start-backend.sh` (`FEATURE_SCREENING_RUNS=true`, `FEATURE_ROLE_BRIEF=true`,
  `AUTH_MODE=dev_header`, `HR_SYSTEM_ADAPTER=mock`, `AI_PROVIDER=mock`, DB
  `hr_phase1_rolebrief_copy.db`) and the frontend from `scripts/start-frontend.sh`
  (`NEXT_PUBLIC_DEV_AUTH=true`, `NEXT_PUBLIC_FEATURE_SCREENING_RUNS=true`,
  `NEXT_PUBLIC_FEATURE_ROLE_BRIEF=true`). The walkthrough shows:
  1. "Recruiter bu-1" starts `REQ-OPEN-1`. The page reaches `awaiting_role_approval` and
     phase_1 `awaiting_approval`, and shows the brief with facts (path + quote), AI
     inferences and ambiguities in separate sections.
  2. "Recruiter bu-1" clicks Approve and sees the `role_brief:approve` 403 message.
  3. "Approver bu-1" clicks Approve. The page shows `role_configuration`, phase_1
     `completed`, and approved by/at.
  4. A `REQ-AI-INVALID-1` run shows `blocked` with the output-invalid label and no brief.

**Reversibility:** `NEXT_PUBLIC_FEATURE_ROLE_BRIEF=false` (the default) restores today's
page exactly: polling stops at `role_brief_draft` and no panel or approve button is shown.
There is no migration. Reverting the branch removes the panel, the API functions and the
preset. Briefs and approvals made through the UI stay in the copy DB and are never deleted.

**Deferred from Phase 7:** brief editing and re-generation UI; a view of the raw snapshot
next to the citations (the quotes are shown instead, and the raw payload stays unexposed per
D-11); a separate role-brief page or list; frontend tests (D-18); accessibility and design
pass.

### Feature-level deferred list (Role Brief)

| Item | Reason |
|---|---|
| Editing, re-generating or retrying a brief | Kickoff out of scope. D-33: retry = start a new run (the snapshot is reused by hash). |
| Clarification workflow with HR, `awaiting_role_review` | Kickoff out of scope. Ambiguities are shown and accepted on approval (D-38, Q-27). |
| Phase 2 role configuration | Kickoff out of scope. Runs stop at `role_configuration`. |
| Re-ingestion on source version change | Kickoff out of scope (Tech Arch §5.1 design control). |
| Multiple AI providers, fallback, routing | Kickoff out of scope. The gateway (D-39) is the seam. |
| Secret manager for `GROQ_API_KEY` | Laptop demo (D-31). Tech Arch §9 secret manager before pilot. |
| Recovery of runs stuck in `role_brief_draft` | Q-24. |
| PostgreSQL verification | Deferred by the user (D-30/Q-21). Code stays dialect-neutral (D-28). |
| AI quality evaluation and bias checks | Tech Arch §9/§13. Required before pilot, not for the demo. |
| Trimmed tests (see Phase 6 deferred) | D-18. Restore at the pre-pilot revisit. |

### Open questions for approval (Role Brief)

Numbered from Q-22 so they do not collide with Q-1…Q-21.

**Resolved 2026-10-22:** the user approved all defaults (Q-22…Q-28).

- **Q-22** Approve or amend D-32…D-39 (defaults are listed in `docs/DECISIONS.md`).
- **Q-23** Data leaving the laptop: requisition text is sent to Groq, a third-party cloud
  API (Tech Arch §15 residency and retention are open). Is it acceptable for the demo to use
  only the synthetic mock HR fixtures with Groq? The default is yes: mock HR fixtures only,
  with no real requisition data.
- **Q-24** Runs interrupted mid-generation (backend restart) stay in `role_brief_draft`, and
  the UI shows "Still running — use Refresh". Should startup recovery block them as
  `role_brief_ai_unavailable` (`error_code: interrupted`) after a threshold? The default is
  no for the demo (deferred). It is about one recovery query plus an audit event.
- **Q-25** Citation strictness (D-36): one unverified quote rejects the whole brief. The
  alternative is to keep the brief and move the unverified item into `ambiguities`. The
  default is to reject (fail closed). If the Groq smoke shows frequent rejections, revisit
  this.
- **Q-26** Separation of duties: may the user who started the run approve its brief? The
  default is yes (only `role_brief:approve` is checked). The alternative is to refuse with
  409/403 when `approved_by == started_by`.
- **Q-27** Tech Arch §5.1 step 8 names `awaiting_role_review` for material ambiguity, but
  the Data Model §7.1 and Tech Arch §8.1 state lists do not include it. The default is to
  always go to `awaiting_role_approval`, show material ambiguities, and treat approval as
  explicitly accepting them (System Design §5: "resolved or explicitly accepted"). Confirm.
- **Q-28** Model: `openai/gpt-oss-120b` with temperature 0 and JSON-schema output (D-37).
  Is a smaller or faster Groq model wanted for the demo? Should a configured fallback model
  exist? The default is no fallback; change `AI_MODEL` to switch.

---

### Note 2026-10-22 — PostgreSQL re-verified after D-40

PostgreSQL became the default database again (D-40). The deferred PostgreSQL check from
Phase 5 (Q-21) was run once by the orchestrator on the current code (Phase 6 worktree,
`324bcb4`) against the copy `hr_phase1_mvpui_copy`: `pytest -q` → **75 passed, 0 skipped**
(all 10 `pg_only` tests ran); `alembic upgrade head` → `downgrade -1` → `upgrade head`
clean, `current` = `0003_role_briefs (head)`. The offline-SQL byte-diff against the
pre-Phase-5 baseline was not taken (no baseline exists) and stays deferred.

---

## Feature: Candidates (3A) — applicant import

- **Kickoff:** `docs/prompts/kickoffs/2026-10-22-candidates-3a.md`
- **Plan status:** PROPOSED by the solution-architect, 2026-10-22 — awaiting user approval.
  D-41 records the user's choices (Accepted); D-42…D-47 are Proposed defaults so the plan
  can be built. Build one phase at a time (D-18: small, minimal testing, speed).
- **Plan author:** solution-architect, 2026-10-22
- **Specs used:** System Design §7.1 (3A), §7.3 (identity); Technical Architecture §4.3
  (applicants/identity modules), §5.3, §6.1, §9 (PII); Data Model §4.6 (`candidate`),
  §4.7 (`candidate_source_record`), §4.8 (`candidate_profile_field`), §7.2, §8.
- **Decisions relied on:** D-06, D-08, D-09, D-11, D-12, D-13, D-18, D-20, D-24, D-26, D-28,
  D-32, D-38, D-40, and the new D-41…D-47.
- **Starting point (verified 2026-10-22):** migrations stop at `0003_role_briefs`;
  `candidate` and `candidate_source_record` do **not** exist yet (created in `0004`).
  `RunStatus` already defines `role_configuration`, `sourcing`, `candidate_pool_ready`
  (`backend/app/modules/requisitions/constants.py`). After role-brief approval
  (`RoleBriefService.approve`) the run is in `role_configuration`. The mock HR adapter and
  fixtures live in `backend/app/modules/integrations/adapters/hr_system/`. The executor
  chain is composed in `app/main.py` (`chain_run_handlers`) and run per `RunHandler`
  (`requisitions/service.py`). Phases 6–7 (role brief) are the pattern this feature mirrors.
- **Feature flags (reversibility, D-02):** backend `FEATURE_APPLICANT_SOURCING` (default
  `false`, requires `FEATURE_SCREENING_RUNS=true`); frontend `NEXT_PUBLIC_FEATURE_CANDIDATES`
  (default `false`). Off restores today's behaviour exactly.

### Standing-rule compliance (applies to every task below)

- **D-01:** `0004` only adds tables, indexes and constraints; drops happen only in
  `downgrade()`. No existing table, column, endpoint or page is altered destructively.
- **D-02:** `0004` ships a tested downgrade and a round-trip test. Sourcing and the UI sit
  behind flags that default off. Import failures block the run; nothing is deleted.
- **D-03:** Each phase starts with its own worktree outside `/home/user/HR_phase1`, against a
  database copy.
- **D-04:** The candidates endpoint names its permission (`screening_run:read`). Candidate
  rows are scoped in the repository by their run's business unit (reusing
  `principal_scope_filter`), derived from the principal only.
- **D-28:** Code and `0004` stay dialect-neutral; tests run on PostgreSQL (default, D-40) or
  SQLite (D-26).

### Status flow added by this feature (Data Model §7.1 subset)

```
role_configuration ──claim──▶ sourcing ──imported (N≥0)──▶ candidate_pool_ready
        │                        │
        │                        └──adapter failure / malformed applicant──▶ blocked (+ completion_reason)
        └ (reached when the role brief is approved, D-32/D-38; Phase 2 role-config intelligence is unbuilt and skipped)
```

---

### Phase 8 — Backend: applicants module, mock applicant adapter, migration 0004, import service, GET candidates

Goal: after the role brief is approved, import the requisition's applicants from the mock
adapter into a candidate pool (`candidate` + `candidate_source_record`), move the run
`role_configuration → sourcing → candidate_pool_ready`, and serve the pool over HTTP. All
behind `FEATURE_APPLICANT_SOURCING` (default off).

- [ ] BE-8.1 Isolation setup (D-03). Create worktree
  `/home/user/HR_phase1-worktrees/candidates-phase8` on a branch off `master` (role brief
  Phase 6 already merged). Create a database copy and migrate it to `0003_role_briefs`.
  Done-when: the report shows `git worktree list` with the Phase 8 path and `alembic current`
  showing `0003_role_briefs (head)` on the copy.
- [ ] BE-8.2 Settings, feature flag and env example (D-02, mirrors D-32). In
  `app/core/settings.py` add `FEATURE_APPLICANT_SOURCING` (default `false`) and validate it
  requires `FEATURE_SCREENING_RUNS=true`; reuse `HR_SYSTEM_ADAPTER` for the applicant source
  (D-44). Add the flag to `backend/.env.example` (commented, default off).
  Done-when: `tests/test_settings.py::test_applicant_sourcing_requires_screening_runs` asserts
  the default is `false` and that enabling it without `FEATURE_SCREENING_RUNS` raises.
- [ ] BE-8.3 Mock applicant adapter + fixtures (D-44, D-13). Add `list_applicants(external_requisition_id)`
  to the HR adapter contract (`adapters/hr_system/base.py`) and `MockHRSystemAdapter`, plus
  an `ApplicantPayload` schema (name, headline, skills, years_experience, education, cv_text,
  `external_application_id`). Add fixtures under
  `adapters/hr_system/fixtures/applicants/`: `REQ-OPEN-1.json` (N full applicants),
  `REQ-EMPTY-1.json` (empty list), `REQ-APPLICANTS-MALFORMED.json` (one malformed applicant).
  Field locations only in errors (no PII in messages), like `get_requisition`.
  Done-when: `tests/test_applicant_adapter.py::test_mock_lists_and_rejects_malformed` asserts
  REQ-OPEN-1 returns N validated `ApplicantPayload`s and the malformed fixture raises
  `InvalidHRResponse`.
- [ ] BE-8.4 Migration `0004_candidates` and models (D-01, D-02, D-28, D-47). Create
  `candidate` (§4.6: `identity_status`, timestamps), `candidate_source_record` (§4.7:
  `candidate_id` FK, `screening_run_id` FK, `source_type`, `source_system_key`,
  `external_application_id`, `payload_reference`, `payload_hash`, `normalization_status`,
  timestamps) and `candidate_source_payload` (restricted JSONB + `payload_hash`, mirroring
  `requisition_snapshot_payload`, D-05). Dialect-aware like `0003`. No new DB CHECK on
  statuses (additive, D-10). `downgrade()` drops only what it created.
  Done-when: the Alembic round trip `upgrade head → downgrade -1 → upgrade head` is clean and
  `tests/test_migration_0004.py::test_candidates_round_trip` passes on the phase copy.
- [ ] BE-8.5 `applicants` module models + scoped repositories (D-04, D-09, D-43, D-47). Add
  `backend/app/modules/applicants/` (standard seven files). `CandidateRepository` /
  `CandidateSourceRecordRepository` plus a `CandidateSourcePayloadStore` (mirrors
  `DbSnapshotStore`). `list_for_run(run_id, principal)` joins `screening_run` and reuses
  `principal_scope_filter` so rows are visible only within the principal's scope.
  Done-when: `tests/test_candidate_repository.py::test_list_for_run_is_scoped` asserts a
  candidate whose run is out of the principal's business unit is not returned.
- [ ] BE-8.6 Sourcing/import service + executor wiring (D-42, D-32 pattern). Add
  `ApplicantSourcingService` with a `source(run_id)` `RunHandler`: a no-op unless the run is
  in `role_configuration` with no candidates; otherwise claim `role_configuration → sourcing`,
  call `list_applicants` (recorded as an `integration_attempt`, operation
  `list_applicants`), snapshot each applicant payload (hash + reference, D-47), insert one
  `candidate` (1:1) and one `candidate_source_record` (`source_type=hr_applicant`) per
  applicant, then transition `sourcing → candidate_pool_ready` (count may be 0). An empty
  list still reaches `candidate_pool_ready`; an adapter failure or malformed applicant blocks
  the run (`sourcing_source_unavailable` / `sourcing_source_invalid`). Chain the handler after
  the role-brief handler in `app/main.py` (no-op on first dispatch), and re-`dispatch` the run
  from the approve-role-brief flow after its commit (D-42). No applicant PII in logs/audit.
  Done-when: `tests/test_applicant_sourcing.py::test_import_moves_run_to_pool_ready` uses the
  MOCK adapter to run `source` on a run seeded in `role_configuration` and asserts the run is
  `candidate_pool_ready` with N `candidate` + N `candidate_source_record` rows carrying a
  `payload_hash`.
- [ ] BE-8.7 `GET /api/v1/screening-runs/{run_id}/candidates` (D-04, D-11, D-46). Permission
  `screening_run:read`; run loaded via `get_for_principal` (404 when missing/out of scope);
  paginated `{items, total}` where each item has `candidate_id`, `name`, `headline`,
  `top_skills`, `years_experience`, `education` (loaded from the hash-verified payload).
  Mounted only when `FEATURE_APPLICANT_SOURCING=true`.
  Done-when: `tests/test_candidates_api.py::test_list_candidates_scoped` asserts 200 with the
  pool for an in-scope reader, 404 for an out-of-scope run, and 403 without the permission.
- [ ] BE-8.8 OpenAPI re-export (D-23). In `backend/scripts/export_openapi.py` pin
  `FEATURE_APPLICANT_SOURCING=true`; regenerate `backend/openapi.json`.
  Done-when: `backend/openapi.json` contains `/api/v1/screening-runs/{run_id}/candidates` and
  the `CandidateListResponse` schema.
- [ ] BE-8.9 Manual mock smoke (end of Phase 8, D-18 "one real-ish mock smoke"). On the copy
  with the mock adapters and both flags on: start a run for REQ-OPEN-1, approve its role
  brief, and confirm the pool imports; repeat with REQ-EMPTY-1 (→ `candidate_pool_ready`,
  count 0) and REQ-APPLICANTS-MALFORMED (→ `blocked`). Report real output.
  Done-when: the report shows the three runs reaching `candidate_pool_ready` (N / 0) and
  `blocked` respectively.
- [ ] **Phase 8 Done-when:** in the Phase 8 worktree against the copy, the engineer reports
  real output for `ruff check`, `mypy app`, `pytest`, the `0004` round trip
  (`upgrade head → downgrade -1 → upgrade head`), and the BE-8.9 smoke.

**Reversibility (Phase 8):** `FEATURE_APPLICANT_SOURCING=false` leaves the sourcing handler
out of the chain, mounts no candidates route, and re-dispatch after approval is a no-op, so
the run stops at `role_configuration` exactly as today. `0004` downgrade drops the three new
tables and restores `0003_role_briefs`. Imported candidates and runs are never deleted; a
failed import blocks the run (hidden, not deleted).

**Deferred from Phase 8:** identity resolution / dedup and `candidate_profile_field`
(separate `identity` module, D-43/Q-32); proactive discovery (3B); evidence extraction and
scoring (next feature); CV file upload (mock supplies `cv_text` inline); a `phases.phase_3`
field in the run status response (D-45/Q-33); a dedicated `POST …/source-applicants`
endpoint (D-42/Q-30); app-level encryption of candidate payloads (Q-34).

---

### Phase 9 — Frontend: candidate list on the run status page (behind a flag)

**Precondition:** Phase 8 verified, ticked and merged to `master`.

- [ ] FE-9.1 Isolation setup (D-03). Create worktree
  `/home/user/HR_phase1-worktrees/candidates-phase9` off `master` with Phase 8 merged.
  Migrate the frontend's backend copy to `0004`.
  Done-when: the report shows `git worktree list` with the Phase 9 path and `alembic current`
  showing `0004_candidates (head)`.
- [ ] FE-9.2 API function and messages (D-23). Run `npm run gen:api`. Add `getCandidates(runId)`
  to `src/api/screening-runs.ts` and any labels to `src/api/messages.ts`.
  Done-when: `npm run gen:api` regenerates `src/api/schema.d.ts` with the candidates path and
  `npm run typecheck` passes.
- [ ] FE-9.3 UI flag (D-25, D-02, D-46). Add `isCandidatesEnabled()` to `src/features.ts`
  reading `NEXT_PUBLIC_FEATURE_CANDIDATES` (default `false`). No new dev preset: reading the
  pool uses the existing `screening_run:read`, so the current presets suffice.
  Done-when: `tests`/manual check shows the candidate section is hidden when the flag is off.
- [ ] FE-9.4 Candidate list on the run status page (D-20, D-24/D-38). Behind the flag, when the
  run is `candidate_pool_ready`, fetch and render a `Card` with the pool count and, per
  candidate, name, headline, top skills, years of experience and education — all as escaped
  text (React default; no `dangerouslySetInnerHTML`, D-35). Add `candidate_pool_ready` to the
  polling stopping statuses only when the flag is on (additive to D-24/D-38).
  Done-when: `npm run build`, `npm run lint` and `npm run typecheck` pass and the section
  renders the list for a `candidate_pool_ready` run.
- [ ] FE-9.5 Browser walkthrough (end of Phase 9, D-18 "one browser walkthrough"). With both
  flags on and the backend serving the mock pool, load a `candidate_pool_ready` run and
  confirm the count and candidate fields render. Report what was seen.
  Done-when: the report describes the rendered candidate list for a real backend run.
- [ ] **Phase 9 Done-when:** in the Phase 9 worktree, `npm run build`, `npm run lint` and
  `npm run typecheck` pass, and the FE-9.5 walkthrough is reported.

**Reversibility (Phase 9):** `NEXT_PUBLIC_FEATURE_CANDIDATES=false` hides the candidate
section and leaves D-24/D-38 polling unchanged. No backend change; no schema change.

**Deferred from Phase 9:** a candidate detail page; filtering/sorting the pool; showing
source provenance / raw payload; infinite scroll (simple pagination only).

### Feature-level deferred list (Candidates 3A)

| Deferred | Reason |
|---|---|
| Identity resolution, dedup, `candidate_profile_field`, separate `identity` module | Kickoff out of scope; candidate is 1:1 with the applicant for the MVP (D-43, Q-32). |
| Proactive discovery (3B) | Kickoff out of scope. |
| Evidence extraction and scoring | Next feature. |
| CV file upload | Mock supplies `cv_text` inline. |
| `phases.phase_3` in the run status response | Kept additive for later (D-45, Q-33). |
| `POST …/source-applicants` on-demand endpoint | Automatic trigger chosen (D-42, Q-30). |
| App-level encryption / retention policy for candidate payloads | Dev DB, like D-05 (Q-34). |
| PostgreSQL vs SQLite re-verification depth | Tests run on either (D-28); full PostgreSQL run is the D-40 gate. |

### Open questions for approval (Candidates 3A)

Numbered from Q-29 so they do not collide with Q-1…Q-28.

- **Q-29** Approve or amend D-42…D-47 (defaults are in `docs/DECISIONS.md`).
- **Q-30** Sourcing trigger: re-`dispatch` the run through the executor after role-brief
  approval (chosen default, D-42), a dedicated `POST …/source-applicants`, or run
  automatically whenever a run is observed in `role_configuration`?
- **Q-31** Mock fixtures: how many applicants per requisition (default N=5 for REQ-OPEN-1),
  and which requisitions get an applicant fixture?
- **Q-32** Build a separate `identity` module with dedup / `candidate_profile_field` now, or
  defer it (default: defer; candidate 1:1 applicant)?
- **Q-33** Add a `phases.phase_3` field to the run status response now, or defer (default:
  defer; the `candidate_pool_ready` status plus the candidates endpoint are enough)?
- **Q-34** PII: candidate names and `cv_text` are the first personal data. Is storing them in
  the dev DB unencrypted (mirroring D-05) acceptable until retention/residency (Data Model §9)
  is decided?
- **Q-35** Pagination defaults and the maximum page size for the candidates endpoint.
