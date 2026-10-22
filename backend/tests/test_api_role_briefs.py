"""Role brief API (BE-6.6, D-34, D-38). Mock HR System and mock AI provider only."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.settings import Settings
from app.main import chain_run_handlers, create_app
from app.modules.integrations.adapters.ai_model.mock import MockAIModelAdapter
from app.modules.integrations.adapters.hr_system.mock import MockHRSystemAdapter
from app.modules.requisitions.service import InlineExecutor, build_ingestion_handler
from app.modules.role_briefs.service import build_role_brief_handler
from tests.conftest import database_url, dev_headers

URL = "/api/v1/screening-runs"
APPROVER = dev_headers(
    permissions="screening_run:read,role_brief:approve", principal_id="approver-1"
)


@pytest_asyncio.fixture
async def brief_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        ENVIRONMENT="test",
        DATABASE_URL=database_url(),
        AUTH_MODE="dev_header",
        FEATURE_SCREENING_RUNS=True,
        HR_SYSTEM_ADAPTER="mock",
        RUN_EXECUTOR="inline",
        FEATURE_ROLE_BRIEF=True,
        AI_PROVIDER="mock",
    )
    app = create_app(settings)

    @asynccontextmanager
    async def _scope() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.state.run_executor = InlineExecutor(
        chain_run_handlers(
            build_ingestion_handler(settings, MockHRSystemAdapter(), _scope),
            build_role_brief_handler(settings, MockAIModelAdapter(), _scope),
        )
    )
    app.dependency_overrides[get_session] = _session_override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _start(client: AsyncClient) -> str:
    response = await client.post(
        URL, json={"external_requisition_id": "REQ-OPEN-1"}, headers=dev_headers()
    )
    assert response.status_code == 202
    return str(response.json()["status_url"])


async def test_brief_generated_and_approved_end_to_end(brief_client: AsyncClient) -> None:
    status_url = await _start(brief_client)

    status = (await brief_client.get(status_url, headers=dev_headers())).json()
    assert status["status"] == "awaiting_role_approval"
    assert status["phases"] == {"phase_1": "awaiting_approval"}
    version_id = status["role_brief_version_id"]
    assert version_id

    brief = await brief_client.get(f"{status_url}/role-brief", headers=dev_headers())
    assert brief.status_code == 200
    assert brief.json()["role_brief_version_id"] == version_id
    assert brief.json()["status"] == "awaiting_review"

    approved = await brief_client.post(
        f"{status_url}/approve-role-brief",
        json={"role_brief_version_id": version_id},
        headers=APPROVER,
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["approved_by"] == "approver-1"
    assert approved.json()["approved_at"]

    final = (await brief_client.get(status_url, headers=dev_headers())).json()
    assert final["status"] == "role_configuration"
    assert final["phases"] == {"phase_1": "completed"}


async def test_approve_without_permission_403(brief_client: AsyncClient) -> None:
    status_url = await _start(brief_client)
    version_id = (await brief_client.get(status_url, headers=dev_headers())).json()[
        "role_brief_version_id"
    ]
    response = await brief_client.post(
        f"{status_url}/approve-role-brief",
        json={"role_brief_version_id": version_id},
        headers=dev_headers(),  # recruiter: no role_brief:approve
    )
    assert response.status_code == 403
