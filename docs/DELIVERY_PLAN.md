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
