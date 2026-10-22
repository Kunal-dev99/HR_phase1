"""Requisitions services: snapshots, eligibility, run creation and ingestion.

Services hold the business rules and orchestration. They reach the database only through
repositories, and the HR System only through ``integrations`` services.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable, Collection
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.correlation import is_valid_correlation_id
from app.core.security import Principal
from app.core.settings import RunExecutorKind, Settings
from app.modules.audit.constants import ActorType
from app.modules.audit.schemas import DetailValue
from app.modules.audit.service import AuditService
from app.modules.integrations.adapters.hr_system.base import HRSystemAdapter
from app.modules.integrations.constants import AttemptOutcome
from app.modules.integrations.schemas import HRRequisitionPayload
from app.modules.integrations.service import HRFetchResult, HRSystemService
from app.modules.requisitions import constants as c
from app.modules.requisitions import events
from app.modules.requisitions.constants import AuditReason, CompletionReason, RunStatus
from app.modules.requisitions.models import ScreeningRun
from app.modules.requisitions.repository import (
    DbSnapshotStore,
    RequisitionRepository,
    ScreeningRunRepository,
    SnapshotRepository,
    SnapshotStore,
    compute_payload_hash,
)
from app.modules.requisitions.schemas import (
    EligibilityResult,
    RequisitionUpsert,
    RunPhases,
    RunRequisitionReference,
    ScreeningRunRead,
    ScreeningRunStatusResponse,
    SnapshotCapture,
    SnapshotRead,
)

logger = logging.getLogger("app.requisitions")

# --- Snapshots (BE-1.5, D-05) -------------------------------------------------------------


class SnapshotService:
    def __init__(self, snapshots: SnapshotRepository, store: SnapshotStore) -> None:
        self._snapshots = snapshots
        self._store = store

    @classmethod
    def for_session(cls, session: AsyncSession) -> SnapshotService:
        return cls(SnapshotRepository(session), DbSnapshotStore(session))

    async def capture(
        self,
        *,
        requisition_id: uuid.UUID,
        payload: dict[str, Any],
        external_version: str | None,
    ) -> SnapshotCapture:
        """Pin ``payload`` as a snapshot, reusing the latest one if the hash is unchanged."""
        payload_hash = compute_payload_hash(payload)
        latest = await self._snapshots.latest_for_requisition(requisition_id)
        if latest is not None and latest.payload_hash == payload_hash:
            return SnapshotCapture(snapshot=SnapshotRead.model_validate(latest), reused=True)

        reference, stored_hash = await self._store.put(payload)
        if stored_hash != payload_hash:  # the store must hash exactly what we hashed
            raise RuntimeError("snapshot store returned an unexpected payload hash")
        snapshot = await self._snapshots.add(
            requisition_id=requisition_id,
            external_version=external_version,
            payload_reference=reference,
            payload_hash=payload_hash,
            schema_version=c.REQUISITION_INGESTION_SCHEMA_VERSION,
        )
        return SnapshotCapture(snapshot=SnapshotRead.model_validate(snapshot), reused=False)

    async def load_payload(self, snapshot: SnapshotRead) -> dict[str, Any]:
        """Return the snapshot payload; raises ``SnapshotIntegrityError`` if it was altered."""
        return await self._store.get(snapshot.payload_reference, snapshot.payload_hash)


# --- Eligibility (BE-1.6, D-07) -----------------------------------------------------------


def _normalise_status(value: str) -> str:
    return value.strip().casefold()


def check_eligibility(
    payload: HRRequisitionPayload, eligible_statuses: Collection[str]
) -> EligibilityResult:
    """Pure eligibility check, rules version ``ELIGIBILITY_RULES_VERSION``.

    Eligible when the source status is in ``eligible_statuses`` (compared trimmed and
    case-insensitively) and every field in ``ELIGIBILITY_REQUIRED_FIELDS`` is non-blank.
    A disallowed status is reported first. The payload is never modified and no default is
    ever filled in: a missing field is reported, not invented.
    """
    allowed = {_normalise_status(s) for s in eligible_statuses}
    missing = tuple(
        name
        for name in c.ELIGIBILITY_REQUIRED_FIELDS
        if not isinstance(value := getattr(payload, name), str) or not value.strip()
    )
    if _normalise_status(payload.status) not in allowed:
        reason: CompletionReason | None = CompletionReason.REQUISITION_NOT_ELIGIBLE_STATUS
    elif missing:
        reason = CompletionReason.REQUISITION_INCOMPLETE
    else:
        reason = None
    return EligibilityResult(
        eligible=reason is None,
        reason_code=reason,
        missing_fields=missing,
        rules_version=c.ELIGIBILITY_RULES_VERSION,
    )


# --- Run creation (BE-1.7) ----------------------------------------------------------------


class PermissionDeniedError(PermissionError):
    """The principal lacks the permission for this service call (defence in depth, D-04)."""


class InvalidRunRequestError(ValueError):
    """The run request is malformed (requisition ID or correlation ID)."""


class RunStateConflictError(RuntimeError):
    """The run left the expected state while this unit of work was running."""


class ScreeningRunService:
    """Creates runs. ``create`` joins the caller's unit of work and does not commit."""

    def __init__(
        self,
        runs: ScreeningRunRepository,
        audit: AuditService,
        *,
        hr_system_key: str,
        snapshots: SnapshotRepository | None = None,
        session: AsyncSession | None = None,
    ) -> None:
        self._runs = runs
        self._audit = audit
        self._hr_system_key = hr_system_key
        self._snapshots = snapshots
        self._session = session

    @classmethod
    def for_session(cls, session: AsyncSession, *, hr_system_key: str) -> ScreeningRunService:
        return cls(
            ScreeningRunRepository(session),
            AuditService.for_session(session),
            hr_system_key=hr_system_key,
            snapshots=SnapshotRepository(session),
            session=session,
        )

    async def start(
        self,
        principal: Principal,
        external_requisition_id: str,
        correlation_id: str,
        executor: RunExecutor,
    ) -> ScreeningRunRead:
        """Create the run, commit, and only then dispatch it (BE-2.2, D-06).

        The executor never sees a run whose creation could still roll back.
        """
        if self._session is None:
            raise RuntimeError("start() needs a session-bound service (use for_session)")
        run = await self.create(principal, external_requisition_id, correlation_id)
        await self._session.commit()
        await executor.dispatch(run.id)
        return run

    async def get_status(
        self, principal: Principal, run_id: uuid.UUID
    ) -> ScreeningRunStatusResponse | None:
        """Scoped read (D-09): ``None`` when the run is missing or out of scope."""
        if not principal.has_permission(c.PERMISSION_SCREENING_RUN_READ):
            raise PermissionDeniedError(c.PERMISSION_SCREENING_RUN_READ)
        run = await self._runs.get_for_principal(run_id, principal)
        if run is None:
            return None
        status = RunStatus(run.status)
        requisition: RunRequisitionReference | None = None
        if run.requisition_id is not None:
            snapshot = None
            if run.requisition_snapshot_id is not None and self._snapshots is not None:
                snapshot = await self._snapshots.get(run.requisition_snapshot_id)
            requisition = RunRequisitionReference(
                external_requisition_id=run.external_requisition_id,
                hr_system_key=run.hr_system_key,
                requisition_id=run.requisition_id,
                snapshot_id=run.requisition_snapshot_id,
                payload_hash=snapshot.payload_hash if snapshot else None,
                captured_at=snapshot.captured_at if snapshot else None,
            )
        return ScreeningRunStatusResponse(
            run_id=run.id,
            status=status,
            phases=RunPhases(phase_1=c.PHASE_1_BY_STATUS.get(status, c.PHASE_IN_PROGRESS)),
            completion_reason=(
                CompletionReason(run.completion_reason) if run.completion_reason else None
            ),
            status_details=run.status_details,
            requisition=requisition,
            started_at=run.started_at,
            completed_at=run.completed_at,
            correlation_id=run.correlation_id,
            role_brief_version_id=run.role_brief_version_id,
        )

    async def create(
        self, principal: Principal, external_requisition_id: str, correlation_id: str
    ) -> ScreeningRunRead:
        """Insert a run in ``created`` plus its ``ScreeningRunCreated`` event, atomically."""
        if not principal.has_permission(c.PERMISSION_SCREENING_RUN_CREATE):
            raise PermissionDeniedError(c.PERMISSION_SCREENING_RUN_CREATE)
        external_id = external_requisition_id.strip()
        if not 1 <= len(external_id) <= c.EXTERNAL_REQUISITION_ID_MAX:
            raise InvalidRunRequestError(
                f"external_requisition_id must be 1-{c.EXTERNAL_REQUISITION_ID_MAX} characters"
            )
        if not is_valid_correlation_id(correlation_id):
            raise InvalidRunRequestError("correlation_id is not valid")

        run = await self._runs.add(
            hr_system_key=self._hr_system_key,
            external_requisition_id=external_id,
            started_by=principal.id,
            # Captured from the authenticated principal, never from request input (D-09).
            scope_business_units=sorted(principal.business_units),
            correlation_id=correlation_id,
        )
        await self._audit.record(
            screening_run_id=run.id,
            entity_type=c.ENTITY_SCREENING_RUN,
            entity_id=str(run.id),
            event_type=events.SCREENING_RUN_CREATED,
            actor_type=ActorType.USER,
            actor_id=principal.id,
            correlation_id=run.correlation_id,
            details={
                "status": run.status,
                "hr_system_key": run.hr_system_key,
                "external_requisition_id": run.external_requisition_id,
            },
        )
        return ScreeningRunRead.model_validate(run)


# --- Ingestion (BE-1.7, D-06, D-07, D-09, D-12) -------------------------------------------

_ERROR_REASONS: dict[AttemptOutcome, CompletionReason] = {
    AttemptOutcome.NOT_FOUND: CompletionReason.REQUISITION_NOT_FOUND,
    AttemptOutcome.UNAVAILABLE: CompletionReason.HR_SYSTEM_UNAVAILABLE,
    AttemptOutcome.TIMEOUT: CompletionReason.HR_SYSTEM_UNAVAILABLE,
    AttemptOutcome.INVALID_RESPONSE: CompletionReason.HR_RESPONSE_INVALID,
}


def _in_scope(business_unit: str, scope_business_units: Collection[str]) -> bool:
    """D-09: the starter's scope covers the requisition's business unit (``*`` if granted)."""
    return business_unit in scope_business_units or c.WILDCARD_BUSINESS_UNIT in scope_business_units


class IngestionService:
    """Drives a run from ``created`` to ``role_brief_draft`` or ``blocked``.

    The work is split into units of work, each committed on success and rolled back on
    failure, so no transaction stays open across the external HR System call:

    1. claim the run (``created -> ingesting_requisition``) and audit it;
    2. call the HR System and record the ``integration_attempt``;
    3. resolve: block, or upsert + snapshot + pin + eligibility + final transition.

    Every status change and its audit event share one unit of work (D-12).
    """

    def __init__(
        self,
        session: AsyncSession,
        hr_system: HRSystemService,
        *,
        eligible_statuses: Collection[str],
    ) -> None:
        self._session = session
        self._hr_system = hr_system
        self._eligible_statuses = tuple(eligible_statuses)
        self._runs = ScreeningRunRepository(session)
        self._requisitions = RequisitionRepository(session)
        self._snapshots = SnapshotService.for_session(session)
        self._audit = AuditService.for_session(session)

    async def _unit_of_work[T](self, work: Callable[[], Awaitable[T]]) -> T:
        try:
            result = await work()
        except BaseException:
            await self._session.rollback()
            raise
        await self._session.commit()
        return result

    async def ingest(self, run_id: uuid.UUID) -> ScreeningRunRead | None:
        """Ingest the run's requisition. Returns ``None`` if another worker owns the run."""
        claimed = await self._unit_of_work(lambda: self._claim(run_id))
        if claimed is None:
            return None
        fetch = await self._unit_of_work(lambda: self._fetch(claimed))
        return await self._unit_of_work(lambda: self._resolve(claimed, fetch))

    async def _claim(self, run_id: uuid.UUID) -> ScreeningRunRead | None:
        current = await self._runs.get_for_workflow(run_id)
        if current is None or current.status != RunStatus.CREATED:
            return None
        if current.hr_system_key != self._hr_system.hr_system_key:
            raise RunStateConflictError("run was requested for a different HR System")
        run = await self._runs.claim_for_ingestion(run_id)
        if run is None:
            return None  # lost the race: a no-op
        await self._record_transition(
            run, RunStatus.CREATED, RunStatus.INGESTING_REQUISITION, AuditReason.INGESTION_CLAIMED
        )
        return ScreeningRunRead.model_validate(run)

    async def _fetch(self, run: ScreeningRunRead) -> HRFetchResult:
        return await self._hr_system.fetch_requisition(
            screening_run_id=run.id,
            external_requisition_id=run.external_requisition_id,
            correlation_id=run.correlation_id,
        )

    async def _resolve(self, run: ScreeningRunRead, fetch: HRFetchResult) -> ScreeningRunRead:
        if fetch.error is not None or fetch.payload is None:
            # Not found / unavailable / invalid: nothing is stored about the requisition.
            reason = _ERROR_REASONS.get(
                fetch.attempt.outcome, CompletionReason.HR_SYSTEM_UNAVAILABLE
            )
            return await self._block(run, reason)

        payload = fetch.payload
        scope = await self._scope_of(run.id)
        if not _in_scope(payload.business_unit, scope):
            # D-09: indistinguishable from not found; only the audit has the true reason.
            return await self._block(
                run,
                CompletionReason.REQUISITION_NOT_FOUND,
                audit_reason=AuditReason.REQUISITION_NOT_ACCESSIBLE,
            )

        requisition = await self._requisitions.upsert(
            RequisitionUpsert(
                hr_system_key=run.hr_system_key,
                external_requisition_id=payload.external_requisition_id,
                external_version=payload.external_version,
                source_status=payload.status,
                business_unit_key=payload.business_unit,
                last_source_modified_at=payload.last_modified_at,
            )
        )
        await self._record(
            run,
            entity_type=c.ENTITY_REQUISITION,
            entity_id=str(requisition.id),
            event_type=events.REQUISITION_FETCHED,
            details={
                "hr_system_key": requisition.hr_system_key,
                "external_requisition_id": requisition.external_requisition_id,
                "external_version": requisition.external_version,
                "source_status": requisition.source_status,
            },
        )
        # Snapshotted and pinned even when not eligible, for traceability (BE-1.7).
        capture = await self._snapshots.capture(
            requisition_id=requisition.id,
            payload=payload.source_document(),
            external_version=payload.external_version,
        )
        await self._record(
            run,
            entity_type=c.ENTITY_REQUISITION_SNAPSHOT,
            entity_id=str(capture.snapshot.id),
            event_type=events.REQUISITION_SNAPSHOT_CAPTURED,
            details={
                "payload_hash": capture.snapshot.payload_hash,
                "schema_version": capture.snapshot.schema_version,
                "reused": capture.reused,
            },
        )

        eligibility = check_eligibility(payload, self._eligible_statuses)
        pins: dict[str, Any] = {
            "requisition_id": requisition.id,
            "requisition_snapshot_id": capture.snapshot.id,
            "business_unit_key": requisition.business_unit_key,
        }
        if eligibility.eligible:
            updated = await self._transition(
                run.id, RunStatus.ROLE_BRIEF_DRAFT, AuditReason.REQUISITION_ELIGIBLE, **pins
            )
        else:
            if eligibility.reason_code is None:  # invariant of EligibilityResult
                raise RuntimeError("ineligible result without a reason code")
            details: dict[str, Any] = {"rules_version": eligibility.rules_version}
            if eligibility.missing_fields:
                details["missing_fields"] = list(eligibility.missing_fields)
            if eligibility.reason_code is CompletionReason.REQUISITION_NOT_ELIGIBLE_STATUS:
                details["source_status"] = payload.status
            updated = await self._transition(
                run.id,
                RunStatus.BLOCKED,
                eligibility.reason_code,
                completion_reason=eligibility.reason_code.value,
                status_details=details,
                completed=True,
                **pins,
            )
        return updated

    async def _scope_of(self, run_id: uuid.UUID) -> list[str]:
        current = await self._runs.get_for_workflow(run_id)
        if current is None:
            raise RunStateConflictError("run disappeared during ingestion")
        return list(current.scope_business_units)

    async def _block(
        self,
        run: ScreeningRunRead,
        reason: CompletionReason,
        *,
        audit_reason: str | None = None,
    ) -> ScreeningRunRead:
        return await self._transition(
            run.id,
            RunStatus.BLOCKED,
            audit_reason or reason,
            completion_reason=reason.value,
            completed=True,
        )

    async def _transition(
        self, run_id: uuid.UUID, new_status: RunStatus, reason_code: str, **fields: Any
    ) -> ScreeningRunRead:
        updated = await self._runs.transition(
            run_id, expected_status=RunStatus.INGESTING_REQUISITION, new_status=new_status, **fields
        )
        if updated is None:
            raise RunStateConflictError("run is no longer ingesting_requisition")
        await self._record_transition(
            updated, RunStatus.INGESTING_REQUISITION, new_status, reason_code
        )
        logger.info(
            "screening run status changed",
            extra={
                "event": "run_status_changed",
                "screening_run_id": str(run_id),
                "correlation_id": updated.correlation_id,
            },
        )
        return ScreeningRunRead.model_validate(updated)

    async def _record_transition(
        self, run: ScreeningRun, old: RunStatus, new: RunStatus, reason_code: str
    ) -> None:
        await self._record(
            ScreeningRunRead.model_validate(run),
            entity_type=c.ENTITY_SCREENING_RUN,
            entity_id=str(run.id),
            event_type=events.RUN_STATUS_CHANGED,
            reason_code=reason_code,
            details={"from_status": old.value, "to_status": new.value},
        )

    async def _record(
        self,
        run: ScreeningRunRead,
        *,
        entity_type: str,
        entity_id: str,
        event_type: str,
        details: dict[str, DetailValue],
        reason_code: str | None = None,
    ) -> None:
        await self._audit.record(
            screening_run_id=run.id,
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=event_type,
            actor_type=ActorType.SYSTEM,
            actor_id=c.INGESTION_ACTOR_ID,
            correlation_id=run.correlation_id,
            reason_code=reason_code,
            details=details,
        )


# --- Run execution and startup recovery (BE-2.2, D-06) ------------------------------------

SessionScope = Callable[[], AbstractAsyncContextManager[AsyncSession]]
RunHandler = Callable[[uuid.UUID], Awaitable[None]]


class RunExecutor(Protocol):
    async def dispatch(self, run_id: uuid.UUID) -> None:
        """Start executing a committed run. Call only after the creating commit."""
        ...

    async def shutdown(self) -> None:
        """Wait for in-flight work to finish."""
        ...


class InlineExecutor:
    """Runs the handler to completion inside ``dispatch``. For tests (RUN_EXECUTOR=inline)."""

    def __init__(self, handler: RunHandler) -> None:
        self._handler = handler

    async def dispatch(self, run_id: uuid.UUID) -> None:
        await self._handler(run_id)

    async def shutdown(self) -> None:
        return None


class InProcessExecutor:
    """One asyncio task per run, each with its own DB session. Tasks are awaited on shutdown."""

    def __init__(self, handler: RunHandler) -> None:
        self._handler = handler
        self._tasks: set[asyncio.Task[None]] = set()

    async def _run(self, run_id: uuid.UUID) -> None:
        try:
            await self._handler(run_id)
        except Exception:
            # The run stays in its last committed state; startup recovery handles it.
            logger.exception(
                "screening run execution failed",
                extra={"event": "run_execution_failed", "screening_run_id": str(run_id)},
            )

    async def dispatch(self, run_id: uuid.UUID) -> None:
        task = asyncio.create_task(self._run(run_id), name=f"screening-run-{run_id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def shutdown(self) -> None:
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)


def build_ingestion_handler(
    settings: Settings, adapter: HRSystemAdapter, session_scope: SessionScope
) -> RunHandler:
    """Each dispatched run is ingested in its own session from ``session_scope``."""

    async def _ingest(run_id: uuid.UUID) -> None:
        async with session_scope() as session:
            hr = HRSystemService.for_session(
                session, adapter, timeout_seconds=settings.HR_SYSTEM_TIMEOUT_SECONDS
            )
            ingestion = IngestionService(
                session, hr, eligible_statuses=settings.REQUISITION_ELIGIBLE_SOURCE_STATUSES
            )
            await ingestion.ingest(run_id)

    return _ingest


def build_run_executor(settings: Settings, handler: RunHandler) -> RunExecutor:
    if settings.RUN_EXECUTOR is RunExecutorKind.INLINE:
        return InlineExecutor(handler)
    return InProcessExecutor(handler)


class RunRecoveryService:
    """Startup recovery (D-06): block interrupted ingesting runs, redispatch created ones.

    Runs execute only in-process (``InProcessExecutor``), whose ``shutdown`` awaits every
    in-flight task, so a clean stop leaves no run in ``ingesting_requisition``. Any run found
    in that state at startup therefore lost its worker to a crash and has no owner left: it
    is blocked as ``ingestion_interrupted`` regardless of how long ago it was claimed.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._runs = ScreeningRunRepository(session)
        self._audit = AuditService.for_session(session)

    async def recover(
        self, executor: RunExecutor
    ) -> tuple[list[uuid.UUID], list[uuid.UUID]]:
        """Return ``(redispatched, blocked)`` run IDs."""
        blocked: list[uuid.UUID] = []
        try:
            interrupted = await self._runs.list_ids_in_status(RunStatus.INGESTING_REQUISITION)
            for run_id in interrupted:
                run = await self._runs.transition(
                    run_id,
                    expected_status=RunStatus.INGESTING_REQUISITION,
                    new_status=RunStatus.BLOCKED,
                    completion_reason=CompletionReason.INGESTION_INTERRUPTED.value,
                    completed=True,
                )
                if run is None:
                    continue  # moved on meanwhile
                await self._audit.record(
                    screening_run_id=run.id,
                    entity_type=c.ENTITY_SCREENING_RUN,
                    entity_id=str(run.id),
                    event_type=events.RUN_STATUS_CHANGED,
                    actor_type=ActorType.SYSTEM,
                    actor_id=c.INGESTION_ACTOR_ID,
                    correlation_id=run.correlation_id,
                    reason_code=CompletionReason.INGESTION_INTERRUPTED,
                    details={
                        "from_status": RunStatus.INGESTING_REQUISITION.value,
                        "to_status": RunStatus.BLOCKED.value,
                    },
                )
                blocked.append(run.id)
            created = await self._runs.list_ids_in_status(RunStatus.CREATED)
        except BaseException:
            await self._session.rollback()
            raise
        await self._session.commit()  # dispatch only what is committed
        for run_id in created:
            await executor.dispatch(run_id)
        return created, blocked
