"""HR System mock adapter, factory, timeout and integration_attempt recording (BE-1.4)."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import Environment, Settings, UnsafeConfigurationError
from app.modules.integrations.adapters.hr_system.base import (
    HRSystemUnavailable,
    InvalidHRResponse,
    RequisitionNotFound,
)
from app.modules.integrations.adapters.hr_system.mock import MockHRSystemAdapter
from app.modules.integrations.constants import AttemptOutcome, HRErrorCode
from app.modules.integrations.schemas import HRRequisitionPayload
from app.modules.integrations.service import (
    HRSystemNotConfiguredError,
    HRSystemService,
    build_hr_system_adapter,
)
from app.modules.requisitions.repository import ScreeningRunRepository

URL = "postgresql+asyncpg://u:p@localhost:5432/hr_phase1_p1req_copy"


async def test_fixture_outcomes() -> None:
    adapter = MockHRSystemAdapter()
    assert adapter.hr_system_key == "mock"

    # 1. REQ-OPEN-1: complete and open.
    open_req = await adapter.get_requisition("REQ-OPEN-1")
    assert isinstance(open_req, HRRequisitionPayload)
    assert open_req.status == "open"
    assert open_req.business_unit == "bu-1"
    assert open_req.title and open_req.description

    # 2. REQ-CLOSED-1: closed.
    closed = await adapter.get_requisition("REQ-CLOSED-1")
    assert closed.status == "closed"

    # 3. REQ-INCOMPLETE-1: no description, and none is invented.
    incomplete = await adapter.get_requisition("REQ-INCOMPLETE-1")
    assert incomplete.status == "open"
    assert incomplete.description is None
    assert "description" not in incomplete.source_document()

    # 4. REQ-OTHER-BU-1: business unit bu-other.
    other = await adapter.get_requisition("REQ-OTHER-BU-1")
    assert other.business_unit == "bu-other"

    # 5. REQ-UNAVAILABLE raises HRSystemUnavailable.
    with pytest.raises(HRSystemUnavailable) as unavailable:
        await adapter.get_requisition("REQ-UNAVAILABLE")
    assert unavailable.value.outcome is AttemptOutcome.UNAVAILABLE

    # 6. REQ-MALFORMED fails schema validation, without echoing payload values.
    with pytest.raises(InvalidHRResponse) as malformed:
        await adapter.get_requisition("REQ-MALFORMED")
    assert "status" in str(malformed.value)
    assert "12345" not in str(malformed.value)
    assert malformed.value.outcome is AttemptOutcome.INVALID_RESPONSE

    # 7. Any other ID is not found, including path-like IDs (never used as a path).
    for unknown in ("REQ-NOPE-9", "", "../REQ-OPEN-1", "REQ-OPEN-1.json", "fixtures/REQ-OPEN-1"):
        with pytest.raises(RequisitionNotFound):
            await adapter.get_requisition(unknown)


def test_factory_selects_by_setting_and_fails_closed() -> None:
    def settings(**overrides: object) -> Settings:
        return Settings(_env_file=None, DATABASE_URL=URL, **overrides)  # type: ignore[arg-type]

    for name in ("mock", " Mock "):
        adapter = build_hr_system_adapter(settings(HR_SYSTEM_ADAPTER=name))
        assert isinstance(adapter, MockHRSystemAdapter)
    with pytest.raises(HRSystemNotConfiguredError):
        build_hr_system_adapter(settings())
    with pytest.raises(HRSystemNotConfiguredError, match="unknown"):
        build_hr_system_adapter(settings(HR_SYSTEM_ADAPTER="workday"))
    # Even if settings validation was bypassed, the factory refuses the mock in production.
    unsafe = Settings.model_construct(
        ENVIRONMENT=Environment.PRODUCTION, DATABASE_URL=URL, HR_SYSTEM_ADAPTER="mock"
    )
    with pytest.raises(UnsafeConfigurationError):
        build_hr_system_adapter(unsafe)
    assert settings().HR_SYSTEM_TIMEOUT_SECONDS == 10.0


async def _run_id(session: AsyncSession) -> uuid.UUID:
    run = await ScreeningRunRepository(session).add(
        hr_system_key="mock",
        external_requisition_id="REQ-OPEN-1",
        started_by="alice",
        scope_business_units=["bu-1"],
        correlation_id="corr-attempt-1",
    )
    return run.id


@pytest.mark.pg_only
async def test_integration_attempt_recorded_without_payload(db_session: AsyncSession) -> None:
    run_id = await _run_id(db_session)
    service = HRSystemService.for_session(db_session, MockHRSystemAdapter(), timeout_seconds=5)

    cases = {
        "REQ-OPEN-1": (AttemptOutcome.SUCCESS, None),
        "REQ-UNAVAILABLE": (AttemptOutcome.UNAVAILABLE, HRErrorCode.UNAVAILABLE),
        "REQ-MALFORMED": (AttemptOutcome.INVALID_RESPONSE, HRErrorCode.INVALID_RESPONSE),
        "REQ-NOPE-9": (AttemptOutcome.NOT_FOUND, HRErrorCode.NOT_FOUND),
    }
    for external_id, (outcome, error_code) in cases.items():
        result = await service.fetch_requisition(
            screening_run_id=run_id, external_requisition_id=external_id, correlation_id="corr-1"
        )
        assert (result.payload is None) == (outcome is not AttemptOutcome.SUCCESS)
        assert (result.error is None) == (outcome is AttemptOutcome.SUCCESS)
        assert result.attempt.outcome is outcome
        assert result.attempt.error_code == (error_code.value if error_code else None)

    attempts = await service.list_attempts(run_id)
    assert [a.outcome for a in attempts] == [o for o, _ in cases.values()]
    for attempt in attempts:
        assert attempt.integration_name == "hr_system"
        assert attempt.operation == "get_requisition"
        assert attempt.correlation_id == "corr-1"
        assert attempt.attempt_number == 1
        assert attempt.completed_at is not None and attempt.completed_at >= attempt.started_at
        assert attempt.request_reference is None and attempt.response_reference is None

    # No payload body anywhere in the stored rows.
    open_req = await MockHRSystemAdapter().get_requisition("REQ-OPEN-1")
    rows = await db_session.execute(
        text("SELECT row_to_json(a)::text FROM integration_attempt a WHERE screening_run_id = :r"),
        {"r": run_id},
    )
    stored = " ".join(r[0] for r in rows)
    assert open_req.title and open_req.description
    for secret in (open_req.title, open_req.description, "Apache Spark", "Remote (EU)", "bu-1"):
        assert secret not in stored

    # And the table has no column that could hold one.
    columns = await db_session.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'integration_attempt'"
        )
    )
    names = {r[0] for r in columns}
    assert not names & {"payload", "body", "request_body", "response_body", "raw_payload"}


async def test_per_call_timeout_is_recorded_as_unavailable(db_session: AsyncSession) -> None:
    run_id = await _run_id(db_session)
    slow = MockHRSystemAdapter(latency_seconds=1.0)
    service = HRSystemService.for_session(db_session, slow, timeout_seconds=0.05)
    result = await service.fetch_requisition(
        screening_run_id=run_id, external_requisition_id="REQ-OPEN-1", correlation_id="corr-2"
    )
    assert isinstance(result.error, HRSystemUnavailable)
    assert result.payload is None
    assert result.attempt.outcome is AttemptOutcome.TIMEOUT
    assert result.attempt.error_code == HRErrorCode.TIMEOUT.value


async def test_response_for_another_requisition_is_invalid(db_session: AsyncSession) -> None:
    class WrongIdAdapter(MockHRSystemAdapter):
        async def get_requisition(self, external_requisition_id: str) -> HRRequisitionPayload:
            return await super().get_requisition("REQ-OPEN-1")

    run_id = await _run_id(db_session)
    service = HRSystemService.for_session(db_session, WrongIdAdapter(), timeout_seconds=5)
    result = await service.fetch_requisition(
        screening_run_id=run_id, external_requisition_id="REQ-CLOSED-1", correlation_id="c-3"
    )
    assert isinstance(result.error, InvalidHRResponse)
    assert result.attempt.error_code == HRErrorCode.ID_MISMATCH.value
