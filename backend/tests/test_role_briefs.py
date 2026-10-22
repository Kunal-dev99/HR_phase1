"""Role brief generation service (BE-6.5, D-32, D-33, D-36, D-37). Mock AI provider only."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.modules.audit.service import AuditService
from app.modules.integrations.adapters.ai_model.mock import MockAIModelAdapter
from app.modules.integrations.adapters.hr_system.mock import MockHRSystemAdapter
from app.modules.integrations.service import AIGatewayService, HRSystemService
from app.modules.requisitions.repository import ScreeningRunRepository
from app.modules.requisitions.service import IngestionService, ScreeningRunService
from app.modules.role_briefs.constants import ROLE_BRIEF_PROMPT_VERSION, ROLE_BRIEF_SCHEMA_VERSION
from app.modules.role_briefs.models import RoleBriefVersion
from app.modules.role_briefs.repository import RoleBriefRepository
from app.modules.role_briefs.service import RoleBriefService

STARTER = Principal(
    id="recruiter-1",
    permissions=frozenset({"screening_run:create", "screening_run:read"}),
    business_units=frozenset({"bu-1"}),
)


async def _ingested_run(session: AsyncSession, external_id: str) -> uuid.UUID:
    service = ScreeningRunService.for_session(session, hr_system_key="mock")
    run = await service.create(STARTER, external_id, "corr-brief-0001")
    await session.commit()
    hr = HRSystemService.for_session(session, MockHRSystemAdapter(), timeout_seconds=5)
    await IngestionService(session, hr, eligible_statuses=("open",)).ingest(run.id)
    return run.id


async def _generate(session: AsyncSession, run_id: uuid.UUID) -> uuid.UUID | None:
    gateway = AIGatewayService.for_session(session, MockAIModelAdapter(), timeout_seconds=5)
    return await RoleBriefService(session, gateway=gateway, model="mock-model").generate(run_id)


async def test_generation_creates_brief_and_awaits_approval(db_session: AsyncSession) -> None:
    run_id = await _ingested_run(db_session, "REQ-OPEN-1")
    version_id = await _generate(db_session, run_id)

    run = await ScreeningRunRepository(db_session).get_for_workflow(run_id)
    assert run is not None and version_id is not None
    assert run.status == "awaiting_role_approval"
    assert run.role_brief_version_id == version_id

    brief = await RoleBriefRepository(db_session).get(version_id)
    assert brief is not None
    assert brief.status == "awaiting_review"
    assert brief.model_provider == "mock" and brief.model_name == "mock-role-brief"
    assert brief.prompt_version == ROLE_BRIEF_PROMPT_VERSION
    assert brief.schema_version == ROLE_BRIEF_SCHEMA_VERSION
    assert brief.source_payload_hash.startswith("sha256:")
    assert brief.source_snapshot_id == run.requisition_snapshot_id

    attempts = await HRSystemService.for_session(
        db_session, MockHRSystemAdapter(), timeout_seconds=5
    ).list_attempts(run_id)
    ai_attempts = [a for a in attempts if a.integration_name == "ai_model"]
    assert len(ai_attempts) == 1 and ai_attempts[0].outcome == "success"

    events = await AuditService.for_session(db_session).list_for_run(run_id)
    created = [e for e in events if e.event_type == "RoleBriefCreated"]
    assert len(created) == 1 and created[0].actor_id == "role_briefs.generator"


async def test_invalid_ai_output_blocks_run(db_session: AsyncSession) -> None:
    run_id = await _ingested_run(db_session, "REQ-AI-INVALID-1")
    assert await _generate(db_session, run_id) is None

    run = await ScreeningRunRepository(db_session).get_for_workflow(run_id)
    assert run is not None
    assert run.status == "blocked"
    assert run.completion_reason == "role_brief_output_invalid"
    assert run.status_details is not None
    assert run.status_details["error_code"] == "citation_unverified"
    assert run.role_brief_version_id is None
    count = await db_session.scalar(
        select(func.count())
        .select_from(RoleBriefVersion)
        .where(RoleBriefVersion.screening_run_id == run_id)
    )
    assert count == 0
