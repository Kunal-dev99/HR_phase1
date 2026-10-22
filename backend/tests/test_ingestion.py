"""Run creation and ingestion services (BE-1.7, D-07, D-09, D-12)."""

import json
import uuid
from dataclasses import dataclass
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.modules.audit.constants import ActorType
from app.modules.audit.schemas import AuditEventRead
from app.modules.audit.service import AuditService
from app.modules.integrations.adapters.hr_system.mock import FIXTURES_DIR, MockHRSystemAdapter
from app.modules.integrations.constants import AttemptOutcome
from app.modules.integrations.schemas import HRRequisitionPayload
from app.modules.integrations.service import HRSystemService
from app.modules.requisitions.constants import CompletionReason, RunStatus
from app.modules.requisitions.repository import (
    RequisitionRepository,
    ScreeningRunRepository,
)
from app.modules.requisitions.schemas import ScreeningRunRead, SnapshotRead
from app.modules.requisitions.service import (
    IngestionService,
    InvalidRunRequestError,
    PermissionDeniedError,
    ScreeningRunService,
    SnapshotService,
)

STARTER = Principal(
    id="recruiter-1",
    permissions=frozenset({"screening_run:create", "screening_run:read"}),
    business_units=frozenset({"bu-1"}),
)
CORRELATION_ID = "corr-ingest-0001"


@dataclass
class Outcome:
    run: ScreeningRunRead
    events: list[AuditEventRead]


async def _create(
    session: AsyncSession, external_id: str, principal: Principal = STARTER
) -> uuid.UUID:
    service = ScreeningRunService.for_session(session, hr_system_key="mock")
    run = await service.create(principal, external_id, CORRELATION_ID)
    await session.commit()  # the caller's unit of work (releases the test savepoint)
    return run.id


def _ingestion(
    session: AsyncSession, adapter: MockHRSystemAdapter | None = None
) -> IngestionService:
    hr = HRSystemService.for_session(session, adapter or MockHRSystemAdapter(), timeout_seconds=5)
    return IngestionService(session, hr, eligible_statuses=("open",))


async def _start_and_ingest(
    session: AsyncSession, external_id: str, principal: Principal = STARTER
) -> Outcome:
    run_id = await _create(session, external_id, principal)
    result = await _ingestion(session).ingest(run_id)
    assert result is not None
    events = await AuditService.for_session(session).list_for_run(run_id)
    return Outcome(run=result, events=events)


async def _count(session: AsyncSession, sql: str, **params: Any) -> int:
    return int(await session.scalar(text(sql), params) or 0)


async def _stored_nothing(session: AsyncSession, external_id: str) -> None:
    """No requisition and therefore no snapshot exists for this external ID."""
    assert await RequisitionRepository(session).get_by_external_id("mock", external_id) is None
    assert await _count(session, "SELECT count(*) FROM requisition_snapshot") == 0
    assert await _count(session, "SELECT count(*) FROM requisition_snapshot_payload") == 0


def _transitions(events: list[AuditEventRead]) -> list[tuple[str | None, str | None, str | None]]:
    return [
        (
            str(e.details["from_status"]) if e.details else None,
            str(e.details["to_status"]) if e.details else None,
            e.reason_code,
        )
        for e in events
        if e.event_type == "RunStatusChanged"
    ]


def _assert_blocked_unresolved(run: ScreeningRunRead, reason: CompletionReason) -> None:
    assert run.status is RunStatus.BLOCKED
    assert run.completion_reason is reason
    assert run.completed_at is not None
    assert run.requisition_id is None
    assert run.requisition_snapshot_id is None
    assert run.business_unit_key is None
    assert run.status_details is None


def _assert_audit_conventions(outcome: Outcome) -> None:
    created, *workflow = outcome.events
    assert created.event_type == "ScreeningRunCreated"
    assert created.actor_type is ActorType.USER
    assert created.actor_id == STARTER.id
    for event in workflow:
        assert event.actor_type is ActorType.SYSTEM
        assert event.actor_id == "requisitions.ingestion"
    for event in outcome.events:
        assert event.correlation_id == outcome.run.correlation_id == CORRELATION_ID
        assert event.screening_run_id == outcome.run.id
        assert event.timestamp is not None
    stamps = [e.timestamp for e in outcome.events]
    assert stamps == sorted(stamps)


# --- one test per fixture outcome -------------------------------------------------------


async def test_open_requisition_reaches_role_brief_draft(db_session: AsyncSession) -> None:
    outcome = await _start_and_ingest(db_session, "REQ-OPEN-1")
    run = outcome.run
    assert run.status is RunStatus.ROLE_BRIEF_DRAFT
    assert run.completion_reason is None
    assert run.completed_at is None
    assert run.business_unit_key == "bu-1"
    assert run.requisition_id is not None and run.requisition_snapshot_id is not None
    assert run.started_by == STARTER.id

    requisition = await RequisitionRepository(db_session).get(run.requisition_id)
    assert requisition is not None
    assert (requisition.external_requisition_id, requisition.source_status) == (
        "REQ-OPEN-1",
        "open",
    )
    assert requisition.external_version == "3"

    snapshot = await SnapshotService.for_session(db_session)._snapshots.get(
        run.requisition_snapshot_id
    )
    assert snapshot is not None and snapshot.requisition_id == requisition.id
    payload = await SnapshotService.for_session(db_session).load_payload(
        SnapshotRead.model_validate(snapshot)
    )
    raw = (FIXTURES_DIR / "REQ-OPEN-1.json").read_text()
    # The validated source document: same keys as received, values as validated.
    assert payload == HRRequisitionPayload.model_validate_json(raw).source_document()
    assert set(payload) == set(json.loads(raw))
    assert payload["last_modified_at"] == "2026-10-20T09:30:00Z"

    assert [e.event_type for e in outcome.events] == [
        "ScreeningRunCreated",
        "RunStatusChanged",
        "RequisitionFetched",
        "RequisitionSnapshotCaptured",
        "RunStatusChanged",
    ]
    assert _transitions(outcome.events) == [
        ("created", "ingesting_requisition", "ingestion_claimed"),
        ("ingesting_requisition", "role_brief_draft", "requisition_eligible"),
    ]
    _assert_audit_conventions(outcome)

    attempts = await HRSystemService.for_session(
        db_session, MockHRSystemAdapter(), timeout_seconds=5
    ).list_attempts(run.id)
    assert [(a.outcome, a.correlation_id) for a in attempts] == [
        (AttemptOutcome.SUCCESS, CORRELATION_ID)
    ]


async def test_closed_requisition_blocked_not_eligible_status(db_session: AsyncSession) -> None:
    outcome = await _start_and_ingest(db_session, "REQ-CLOSED-1")
    run = outcome.run
    assert run.status is RunStatus.BLOCKED
    assert run.completion_reason is CompletionReason.REQUISITION_NOT_ELIGIBLE_STATUS
    assert run.status_details == {"rules_version": "1", "source_status": "closed"}
    assert run.completed_at is not None
    # Still snapshotted and pinned for traceability.
    assert run.requisition_id is not None and run.requisition_snapshot_id is not None
    assert run.business_unit_key == "bu-1"
    assert _transitions(outcome.events)[-1] == (
        "ingesting_requisition",
        "blocked",
        "requisition_not_eligible_status",
    )
    _assert_audit_conventions(outcome)


async def test_incomplete_requisition_blocked_with_missing_fields(db_session: AsyncSession) -> None:
    outcome = await _start_and_ingest(db_session, "REQ-INCOMPLETE-1")
    run = outcome.run
    assert run.status is RunStatus.BLOCKED
    assert run.completion_reason is CompletionReason.REQUISITION_INCOMPLETE
    assert run.status_details == {"rules_version": "1", "missing_fields": ["description"]}
    assert run.requisition_id is not None and run.requisition_snapshot_id is not None
    assert _transitions(outcome.events)[-1] == (
        "ingesting_requisition",
        "blocked",
        "requisition_incomplete",
    )
    _assert_audit_conventions(outcome)


async def test_not_found_requisition_blocked(db_session: AsyncSession) -> None:
    outcome = await _start_and_ingest(db_session, "REQ-DOES-NOT-EXIST")
    _assert_blocked_unresolved(outcome.run, CompletionReason.REQUISITION_NOT_FOUND)
    await _stored_nothing(db_session, "REQ-DOES-NOT-EXIST")
    assert [e.event_type for e in outcome.events] == [
        "ScreeningRunCreated",
        "RunStatusChanged",
        "RunStatusChanged",
    ]
    assert _transitions(outcome.events)[-1] == (
        "ingesting_requisition",
        "blocked",
        "requisition_not_found",
    )
    _assert_audit_conventions(outcome)


async def test_other_business_unit_blocked_as_not_found(db_session: AsyncSession) -> None:
    other = await _start_and_ingest(db_session, "REQ-OTHER-BU-1")
    _assert_blocked_unresolved(other.run, CompletionReason.REQUISITION_NOT_FOUND)
    await _stored_nothing(db_session, "REQ-OTHER-BU-1")
    # Only the audit records the true reason (D-09).
    assert _transitions(other.events)[-1] == (
        "ingesting_requisition",
        "blocked",
        "requisition_not_accessible",
    )
    _assert_audit_conventions(other)

    # The run looks exactly like a not-found run to anyone reading it.
    missing = await _start_and_ingest(db_session, "REQ-DOES-NOT-EXIST")
    public = (
        "status",
        "completion_reason",
        "status_details",
        "requisition_id",
        "requisition_snapshot_id",
        "business_unit_key",
        "role_brief_version_id",
    )
    assert {k: getattr(other.run, k) for k in public} == {
        k: getattr(missing.run, k) for k in public
    }

    # The unresolved run stays visible to its starter only.
    runs = ScreeningRunRepository(db_session)
    assert await runs.get_for_principal(other.run.id, STARTER) is not None
    bu_other = Principal(id="x", permissions=frozenset(), business_units=frozenset({"bu-other"}))
    assert await runs.get_for_principal(other.run.id, bu_other) is None

    # Positive control: a starter whose scope covers bu-other ingests it normally.
    wide = Principal(
        id="recruiter-2",
        permissions=STARTER.permissions,
        business_units=frozenset({"bu-1", "bu-other"}),
    )
    allowed = await _start_and_ingest(db_session, "REQ-OTHER-BU-1", wide)
    assert allowed.run.status is RunStatus.ROLE_BRIEF_DRAFT
    assert allowed.run.business_unit_key == "bu-other"


async def test_unavailable_hr_system_blocked(db_session: AsyncSession) -> None:
    outcome = await _start_and_ingest(db_session, "REQ-UNAVAILABLE")
    _assert_blocked_unresolved(outcome.run, CompletionReason.HR_SYSTEM_UNAVAILABLE)
    await _stored_nothing(db_session, "REQ-UNAVAILABLE")
    _assert_audit_conventions(outcome)


async def test_malformed_response_blocked(db_session: AsyncSession) -> None:
    outcome = await _start_and_ingest(db_session, "REQ-MALFORMED")
    _assert_blocked_unresolved(outcome.run, CompletionReason.HR_RESPONSE_INVALID)
    await _stored_nothing(db_session, "REQ-MALFORMED")
    _assert_audit_conventions(outcome)


# --- claims, transactions and invented values ---------------------------------------------


async def test_lost_claim_is_a_noop(db_session: AsyncSession) -> None:
    run_id = await _create(db_session, "REQ-OPEN-1")
    service = _ingestion(db_session)
    assert (await service.ingest(run_id)) is not None
    events_before = len(await AuditService.for_session(db_session).list_for_run(run_id))

    assert await service.ingest(run_id) is None  # already claimed and finished
    assert await service.ingest(uuid.uuid4()) is None  # unknown run
    assert len(await AuditService.for_session(db_session).list_for_run(run_id)) == events_before
    attempts = await _count(
        db_session, "SELECT count(*) FROM integration_attempt WHERE screening_run_id = :r", r=run_id
    )
    assert attempts == 1


async def test_create_validates_and_requires_permission(db_session: AsyncSession) -> None:
    service = ScreeningRunService.for_session(db_session, hr_system_key="mock")
    reader = Principal(
        id="r", permissions=frozenset({"screening_run:read"}), business_units=frozenset()
    )
    with pytest.raises(PermissionDeniedError):
        await service.create(reader, "REQ-OPEN-1", CORRELATION_ID)
    for bad in ("", "   ", "x" * 129):
        with pytest.raises(InvalidRunRequestError):
            await service.create(STARTER, bad, CORRELATION_ID)
    with pytest.raises(InvalidRunRequestError):
        await service.create(STARTER, "REQ-OPEN-1", "not valid!")
    run = await service.create(STARTER, "  REQ-OPEN-1  ", CORRELATION_ID)
    assert run.external_requisition_id == "REQ-OPEN-1"
    assert run.status is RunStatus.CREATED
    stored = await ScreeningRunRepository(db_session).get_for_workflow(run.id)
    assert stored is not None and stored.scope_business_units == ["bu-1"]
    assert await _count(db_session, "SELECT count(*) FROM screening_run") == 1


class _AuditFailureError(RuntimeError):
    pass


def _fail_audit(monkeypatch: pytest.MonkeyPatch, event_type: str, to_status: str | None) -> None:
    original = AuditService.record

    async def record(self: AuditService, **kwargs: Any) -> AuditEventRead:
        details = kwargs.get("details") or {}
        if kwargs["event_type"] == event_type and details.get("to_status") == to_status:
            raise _AuditFailureError(event_type)
        return await original(self, **kwargs)

    monkeypatch.setattr(AuditService, "record", record)


async def _status(session: AsyncSession, run_id: uuid.UUID) -> str | None:
    run = await ScreeningRunRepository(session).get_for_workflow(run_id)
    return None if run is None else run.status


async def test_every_transition_has_audit_event_in_same_transaction(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 1. Every status change in a run's life has exactly one RunStatusChanged event.
    for external_id, final in (("REQ-OPEN-1", "role_brief_draft"), ("REQ-NOPE-1", "blocked")):
        outcome = await _start_and_ingest(db_session, external_id)
        assert outcome.events[0].event_type == "ScreeningRunCreated"
        assert outcome.events[0].details and outcome.events[0].details["status"] == "created"
        path = ["created"] + [to for _, to, _ in _transitions(outcome.events)]
        assert path == ["created", "ingesting_requisition", final]

    # 2. The final transition and its audit rows were written by the same (sub)transaction:
    #    PostgreSQL stamps every row with the writing transaction's id (xmin).
    run_id = outcome.run.id
    run_xmin = await db_session.scalar(
        text("SELECT xmin::text FROM screening_run WHERE id = :r"), {"r": run_id}
    )
    audit_xmins = (
        await db_session.execute(
            text(
                "SELECT xmin::text, details->>'to_status' FROM audit_event "
                "WHERE screening_run_id = :r AND event_type = 'RunStatusChanged' "
                "ORDER BY timestamp"
            ),
            {"r": run_id},
        )
    ).all()
    assert [to for _, to in audit_xmins] == ["ingesting_requisition", "blocked"]
    assert audit_xmins[-1][0] == run_xmin
    assert audit_xmins[0][0] != run_xmin  # the claim was its own unit of work

    # 3. If the audit write fails, the status change it describes does not happen.
    with monkeypatch.context() as patch:
        _fail_audit(patch, "ScreeningRunCreated", None)
        with pytest.raises(_AuditFailureError):
            async with db_session.begin_nested():
                await ScreeningRunService.for_session(db_session, hr_system_key="mock").create(
                    STARTER, "REQ-AUDIT-FAIL", CORRELATION_ID
                )
    assert (
        await _count(
            db_session,
            "SELECT count(*) FROM screening_run WHERE external_requisition_id = 'REQ-AUDIT-FAIL'",
        )
        == 0
    )

    cases = [
        ("REQ-OPEN-1", "ingesting_requisition", "created"),
        ("REQ-OPEN-1", "role_brief_draft", "ingesting_requisition"),
        ("REQ-CLOSED-1", "blocked", "ingesting_requisition"),
        ("REQ-NOPE-2", "blocked", "ingesting_requisition"),
    ]
    for external_id, failing_to_status, status_after in cases:
        run_id = await _create(db_session, external_id)
        snapshots_before = await _count(db_session, "SELECT count(*) FROM requisition_snapshot")
        with monkeypatch.context() as patch:
            _fail_audit(patch, "RunStatusChanged", failing_to_status)
            with pytest.raises(_AuditFailureError):
                await _ingestion(db_session).ingest(run_id)
        assert await _status(db_session, run_id) == status_after, (external_id, failing_to_status)
        run = await ScreeningRunRepository(db_session).get_for_workflow(run_id)
        assert run is not None
        assert run.requisition_snapshot_id is None and run.completion_reason is None
        # Requisition/snapshot writes in the failed unit were rolled back with it.
        assert await _count(db_session, "SELECT count(*) FROM requisition_snapshot") == (
            snapshots_before
        )
        tos = [
            e.details["to_status"]
            for e in await AuditService.for_session(db_session).list_for_run(run_id)
            if e.event_type == "RunStatusChanged" and e.details
        ]
        assert failing_to_status not in tos


async def test_no_values_invented_for_missing_fields(db_session: AsyncSession) -> None:
    outcome = await _start_and_ingest(db_session, "REQ-INCOMPLETE-1")
    run = outcome.run
    assert run.requisition_snapshot_id is not None and run.requisition_id is not None

    # The snapshot is exactly what the HR System sent: no description key, nothing added.
    snapshot = await SnapshotService.for_session(db_session)._snapshots.get(
        run.requisition_snapshot_id
    )
    assert snapshot is not None
    payload = await SnapshotService.for_session(db_session).load_payload(
        SnapshotRead.model_validate(snapshot)
    )
    source = json.loads((FIXTURES_DIR / "REQ-INCOMPLETE-1.json").read_text())
    assert payload == source
    assert "description" not in payload
    for absent in ("responsibilities", "required_skills", "location", "last_modified_at"):
        assert absent not in payload

    # Requisition source fields are copied, and absent ones stay null.
    requisition = await RequisitionRepository(db_session).get(run.requisition_id)
    assert requisition is not None
    assert requisition.last_source_modified_at is None
    assert requisition.external_version == source["external_version"]

    # The run reports the gap instead of filling it; later fields are untouched.
    assert run.status_details == {"rules_version": "1", "missing_fields": ["description"]}
    assert run.role_brief_version_id is None and run.role_configuration_version_id is None

    # No audit event carries a made-up description either.
    for event in outcome.events:
        assert "description" not in (event.details or {})
