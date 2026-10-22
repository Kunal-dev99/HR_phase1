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

- [ ] BE-2.1 Isolation setup (D-03). Create worktree
  `/home/user/HR_phase1-worktrees/p1req-phase2` on branch `feature/p1-requisitions-phase2`,
  based on the reviewed Phase 1 branch. The copy DB is migrated to `0002_requisitions`.
  Done-when: the report shows `git worktree list` with the Phase 2 path, and `alembic current` on the copy shows `0002_requisitions`.
- [ ] BE-2.2 Run executor (**PROPOSED (D-06)**). Add a `RunExecutor` interface with
  `dispatch(run_id)`. `InProcessExecutor` uses an asyncio task with its own DB session,
  started only after the request's transaction commits, and it tracks and awaits tasks on
  shutdown. `InlineExecutor` is for tests. Setting `RUN_EXECUTOR` takes `in_process` (the
  default) or `inline`. On startup, recovery re-dispatches runs in `created`. It blocks
  runs that have stayed in `ingesting_requisition` longer than
  `INGESTION_STALE_AFTER_SECONDS` (default 600), with reason `ingestion_interrupted` and an
  audit event. If `FEATURE_SCREENING_RUNS=true` and `HR_SYSTEM_ADAPTER` is unset, startup
  fails.
  Done-when: `test_executor.py::test_dispatch_after_commit_only`, `test_executor.py::test_startup_recovery_redispatches_created_and_blocks_stale`, and `test_executor.py::test_double_dispatch_ingests_once` pass.
- [ ] BE-2.3 `POST /api/v1/screening-runs`. Permission: `screening_run:create`
  (**PROPOSED (D-08)**). Body: `{"external_requisition_id": str}`, 1–128 chars, trimmed,
  extra fields forbidden (**PROPOSED (D-11)**). The response is `202 Accepted` with body
  `{run_id, status: "created", status_url, correlation_id}`, a `Location` header and an
  `X-Correlation-ID` header. Validation errors return 422. The router calls only
  `ScreeningRunService` and the executor. It never calls a repository. The route is mounted
  only when `FEATURE_SCREENING_RUNS=true`.
  Done-when: `test_api_screening_runs.py::test_post_returns_202_with_run_id_and_status_url`, `test_api_screening_runs.py::test_post_without_principal_401`, and `test_api_screening_runs.py::test_post_without_permission_403` pass.
- [ ] BE-2.4 `GET /api/v1/screening-runs/{run_id}`. Permission: `screening_run:read`
  (**PROPOSED (D-08)**). The row is scoped through
  `ScreeningRunRepository.get_for_principal`. A run that is missing or out of scope
  returns 404 (D-09). The response follows **PROPOSED (D-11)**: `run_id`, `status`,
  `phases` (phase 1 status derived from the run status), `completion_reason`,
  `status_details`, `requisition` ({external_requisition_id, hr_system_key, requisition_id,
  snapshot_id, payload_hash, captured_at}, or null), `started_at`, `completed_at` and
  `correlation_id`. It never includes the raw payload.
  Done-when: `test_api_screening_runs.py::test_get_returns_state_and_phase_status`, `test_api_screening_runs.py::test_get_other_business_unit_404`, and `test_api_screening_runs.py::test_get_without_permission_403` pass.
- [ ] BE-2.5 End-to-end acceptance tests over HTTP (`RUN_EXECUTOR=inline`). Trimmed
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
- [ ] BE-2.6 Safe server access log (Tech Arch §6.2, §9; Phase 0 deviation e). Uvicorn's
  own access log prints query strings, but the app's request log does not. Add
  `--no-access-log` to the `uvicorn` command in `scripts/start-backend.sh`. The app's
  `app.request` JSON log, which records method, path, status, duration and correlation ID,
  then becomes the only access log. This changes only one flag in the dev script, and
  removing the flag reverts it.
  Done-when: during the Phase 2 manual curl check, `GET /healthz?probe=secret-value` against `scripts/start-backend.sh` prints a JSON `app.request` line, and the console contains neither `secret-value` nor a uvicorn access-log line (console excerpt in the report).

**Phase 2 Done-when:** in the Phase 2 worktree against the copy, the engineer reports
real output with every check passing: `ruff check`, `mypy app`, `pytest`, and `alembic
upgrade head && alembic downgrade -1 && alembic upgrade head`. In addition, a manual
`curl` POST and GET against `scripts/start-backend.sh` (with `FEATURE_SCREENING_RUNS=true`,
`AUTH_MODE=dev_header` and `HR_SYSTEM_ADAPTER=mock`) shows 202 followed by
`role_brief_draft` for `REQ-OPEN-1`.

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
